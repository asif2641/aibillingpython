"""tests/test_polish_security.py
=============================
QA Test-First Suite for Phase 7: Activity Log, Database Backups & Data Export,
Purge Sync Queue Command, Global Search, Security Headers & Offline Delta Sync.

Coverage:
1. Activity Log (ActivityLog model, signals, log_activity helper, and view):
   - Happy paths:
     - Creating a Bill automatically creates an ActivityLog entry (action="bill_created", target_type="Bill").
     - Soft-deleting a Bill (is_deleted=True) logs action="bill_deleted".
     - Recording a Payment logs action="payment_recorded".
     - Creating a Party logs action="party_created".
     - Manual call to log_activity(user, action="custom_action", description="Test", metadata={"key": "val"}) persists cleanly.
   - Edge cases:
     - log_activity with user=None or AnonymousUser saves with user=None without raising an error.
     - Activity log view (/en/settings/activity-log/) supports filtering by ?action=bill_created and ?q=...
   - Access control:
     - Unauthenticated user visiting /en/settings/activity-log/ is redirected to login.
     - Staff user without can_manage_shop receives HTTP 403 Forbidden on /en/settings/activity-log/.
     - Superadmin and staff with can_manage_shop=True receive HTTP 200.

2. purge_sync_queue Management Command:
   - Happy path:
     - Processed SyncQueue items with server_timestamp (and processed_at) older than 30 days are deleted when call_command("purge_sync_queue", days=30) runs.
   - Edge cases:
     - Processed SyncQueue items newer than 30 days are preserved.
     - Pending SyncQueue items (status="pending") older than 30 days are NEVER deleted.
     - Failed SyncQueue items (status="failed") older than 30 days are preserved by default, and deleted only when --include-failed is passed.

3. Database Backup & Data Export (backup_db command & views):
   - Happy paths:
     - call_command("backup_db", output_dir=str(tmp_path), retention_days=30) creates a backup_*.json file in tmp_path containing valid JSON with keys shop_profile, categories, units, parties, bills, payments.
     - Old backup_*.json files in output_dir with mtime older than retention_days are automatically pruned.
     - Superadmin GET /en/settings/backups/download-json/ returns HTTP 200 with application/json attachment containing serialized shop data, and does NOT expose user password hashes or SECRET_KEY.
     - Superadmin GET /en/settings/backups/download-csv/ returns HTTP 200 with text/csv attachment containing active bills.
     - Superadmin POST /en/settings/backups/create/ creates a backup and redirects.
   - Access control:
     - Staff without can_manage_shop receives HTTP 403 on /en/settings/backups/, /en/settings/backups/download-json/, /en/settings/backups/download-csv/, and /en/settings/backups/create/.

4. Global Search (/en/search/):
   - Happy paths:
     - Searching /en/search/?q=<invoice_no> finds matching active Bill.
     - Searching /en/search/?q=<party_name> finds matching active Party.
     - Searching /en/search/?q=<item_name> finds matching BillItem.
   - Edge & Security cases:
     - Soft-deleted bills (is_deleted=True) NEVER appear in global search results.
     - Empty search /en/search/?q= returns HTTP 200 with 0 results cleanly.
     - Unauthenticated user visiting /en/search/?q=test is redirected to login.

5. Security Headers & Offline Delta Sync:
   - Security headers: responses include X-Content-Type-Options: nosniff and X-Frame-Options: DENY.
   - Offline delta sync JS check: static/js/offline-sync.js supports last_pulled_at / ?since= parameter for delta pulling.
"""

from __future__ import annotations

import json
import os
import time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.utils import timezone

from bills.models import Bill, BillItem
from categories.models import Category, Unit
from ledger.models import Payment
from ledger.services import record_payment
from parties.models import Party
from settings_app.models import ShopProfile
from sync.models import SyncQueue

User = get_user_model()


def _get_activity_log_model():
    """Import ActivityLog from settings_app.models or billing/accounts if placed there."""
    for mod_path in ("settings_app.models", "accounts.models", "billing.models"):
        try:
            mod = __import__(mod_path, fromlist=["ActivityLog"])
            if hasattr(mod, "ActivityLog"):
                return mod.ActivityLog
        except ImportError:
            continue
    return None


def _get_log_activity_func():
    """Import log_activity helper function from settings_app or common modules."""
    for mod_path in (
        "settings_app.services",
        "settings_app.models",
        "settings_app.utils",
        "billing.utils",
        "accounts.services",
    ):
        try:
            mod = __import__(mod_path, fromlist=["log_activity"])
            if hasattr(mod, "log_activity"):
                return mod.log_activity
        except ImportError:
            continue
    return None


# ===========================================================================
# 1. Activity Log (ActivityLog model, signals, and view)
# ===========================================================================
@pytest.mark.django_db
class TestActivityLog:
    """Tests for ActivityLog model, automatic signal logging, log_activity helper, and view."""

    ACTIVITY_LOG_URL = "/en/settings/activity-log/"

    def test_creating_bill_logs_bill_created(self, staff_user):
        """Creating a Bill automatically creates an ActivityLog entry (action='bill_created', target_type='Bill')."""
        ActivityLog = _get_activity_log_model()
        assert ActivityLog is not None, "ActivityLog model is not implemented."

        party = Party.objects.create(name="Signal Test Vendor", party_type=Party.PartyType.VENDOR)
        bill = Bill.objects.create(
            party=party,
            bill_type=Bill.BillType.PURCHASE,
            invoice_no="ACT-BILL-001",
            grand_total=Decimal("1500.00"),
            created_by=staff_user,
        )

        log_entry = ActivityLog.objects.filter(
            action="bill_created",
            target_type="Bill",
        ).first()
        assert (
            log_entry is not None
        ), "Expected ActivityLog with action='bill_created' and target_type='Bill'."
        if hasattr(log_entry, "target_id") and log_entry.target_id is not None:
            assert str(log_entry.target_id) == str(bill.pk)

    def test_soft_deleting_bill_logs_bill_deleted(self, superadmin_user):
        """Soft-deleting a Bill (is_deleted=True) logs action='bill_deleted'."""
        ActivityLog = _get_activity_log_model()
        assert ActivityLog is not None, "ActivityLog model is not implemented."

        party = Party.objects.create(name="Delete Log Vendor", party_type=Party.PartyType.VENDOR)
        bill = Bill.objects.create(
            party=party,
            bill_type=Bill.BillType.PURCHASE,
            invoice_no="ACT-DEL-001",
            grand_total=Decimal("2000.00"),
            created_by=superadmin_user,
        )

        bill.is_deleted = True
        bill.deleted_at = timezone.now()
        bill.save()

        log_entry = ActivityLog.objects.filter(action="bill_deleted").first()
        assert (
            log_entry is not None
        ), "Expected ActivityLog with action='bill_deleted' when bill is soft-deleted."

    def test_recording_payment_logs_payment_recorded(self, staff_user):
        """Recording a Payment logs action='payment_recorded'."""
        ActivityLog = _get_activity_log_model()
        assert ActivityLog is not None, "ActivityLog model is not implemented."

        party = Party.objects.create(name="Payment Log Vendor", party_type=Party.PartyType.VENDOR)
        payment = record_payment(
            party=party,
            amount=Decimal("500.00"),
            payment_method="cash",
            reference="PAY-LOG-01",
            created_by=staff_user,
        )

        log_entry = ActivityLog.objects.filter(action="payment_recorded").first()
        assert (
            log_entry is not None
        ), "Expected ActivityLog with action='payment_recorded' on Payment creation."
        if hasattr(log_entry, "target_id") and log_entry.target_id is not None:
            assert str(log_entry.target_id) == str(payment.pk)

    def test_creating_party_logs_party_created(self):
        """Creating a Party logs action='party_created'."""
        ActivityLog = _get_activity_log_model()
        assert ActivityLog is not None, "ActivityLog model is not implemented."

        party = Party.objects.create(
            name="New Logged Customer",
            party_type=Party.PartyType.CUSTOMER,
        )

        log_entry = ActivityLog.objects.filter(action="party_created").first()
        assert (
            log_entry is not None
        ), "Expected ActivityLog with action='party_created' on Party creation."
        if hasattr(log_entry, "target_id") and log_entry.target_id is not None:
            assert str(log_entry.target_id) == str(party.pk)

    def test_manual_log_activity_call_persists_cleanly(self, superadmin_user):
        """Manual call to log_activity(user, action='custom_action', description='Test', metadata={'key': 'val'}) persists cleanly."""
        ActivityLog = _get_activity_log_model()
        log_activity = _get_log_activity_func()
        assert ActivityLog is not None, "ActivityLog model is not implemented."
        assert log_activity is not None, "log_activity function is not implemented."

        entry = log_activity(
            user=superadmin_user,
            action="custom_action",
            description="Test custom description",
            metadata={"key": "val"},
        )
        assert entry is not None
        assert entry.pk is not None

        refreshed = ActivityLog.objects.get(pk=entry.pk)
        assert refreshed.user == superadmin_user
        assert refreshed.action == "custom_action"
        assert "Test custom description" in refreshed.description
        assert refreshed.metadata == {"key": "val"}

    def test_log_activity_with_none_or_anonymous_user(self):
        """log_activity with user=None or AnonymousUser saves with user=None without raising an error."""
        ActivityLog = _get_activity_log_model()
        log_activity = _get_log_activity_func()
        assert ActivityLog is not None, "ActivityLog model is not implemented."
        assert log_activity is not None, "log_activity function is not implemented."

        entry_none = log_activity(
            user=None,
            action="system_event",
            description="System task executed",
        )
        assert entry_none.pk is not None
        assert entry_none.user is None

        anon = AnonymousUser()
        entry_anon = log_activity(
            user=anon,
            action="anon_event",
            description="Anonymous action",
        )
        assert entry_anon.pk is not None
        assert entry_anon.user is None

    def test_activity_log_view_filtering_by_action_and_query(
        self, superadmin_client, superadmin_user
    ):
        """Activity log view (/en/settings/activity-log/) supports filtering by ?action=bill_created and ?q=..."""
        log_activity = _get_log_activity_func()
        assert log_activity is not None, "log_activity function is not implemented."

        log_activity(
            user=superadmin_user,
            action="bill_created",
            description="Created invoice INV-FILTER-999",
        )
        log_activity(
            user=superadmin_user,
            action="party_created",
            description="Created party Alpha Beta Traders",
        )

        # Filter by action=bill_created
        res_action = superadmin_client.get(f"{self.ACTIVITY_LOG_URL}?action=bill_created")
        assert res_action.status_code == 200
        content_action = res_action.content.decode("utf-8")
        assert "INV-FILTER-999" in content_action
        assert "Alpha Beta Traders" not in content_action

        # Filter by search query ?q=Alpha Beta
        res_query = superadmin_client.get(f"{self.ACTIVITY_LOG_URL}?q=Alpha+Beta")
        assert res_query.status_code == 200
        content_query = res_query.content.decode("utf-8")
        assert "Alpha Beta Traders" in content_query
        assert "INV-FILTER-999" not in content_query

    def test_activity_log_view_unauthenticated_redirects(self, client):
        """Unauthenticated user visiting /en/settings/activity-log/ is redirected to login."""
        response = client.get(self.ACTIVITY_LOG_URL)
        assert response.status_code == 302
        assert "/login" in response.url or "/accounts/login" in response.url

    def test_activity_log_view_staff_without_permission_forbidden(self, staff_client):
        """Staff user without can_manage_shop receives HTTP 403 Forbidden on /en/settings/activity-log/."""
        response = staff_client.get(self.ACTIVITY_LOG_URL)
        assert response.status_code == 403

    def test_activity_log_view_superadmin_and_permitted_staff_allowed(
        self, superadmin_client, client
    ):
        """Superadmin and staff with can_manage_shop=True receive HTTP 200."""
        res_super = superadmin_client.get(self.ACTIVITY_LOG_URL)
        assert res_super.status_code == 200

        permitted_staff = User.objects.create_user(
            username="permitted_staff_log",
            password="TestPass123!",
            role=User.Role.STAFF,
            can_manage_shop=True,
        )
        client.force_login(permitted_staff)
        res_staff = client.get(self.ACTIVITY_LOG_URL)
        assert res_staff.status_code == 200


# ===========================================================================
# 2. purge_sync_queue Management Command
# ===========================================================================
@pytest.mark.django_db
class TestPurgeSyncQueueCommand:
    """Tests for the purge_sync_queue management command."""

    def _create_queue_item(self, client_id: str, status: str, days_ago: int) -> SyncQueue:
        past_dt = timezone.now() - timedelta(days=days_ago)
        item = SyncQueue.objects.create(
            client_id=client_id,
            record_type=SyncQueue.RecordType.BILL,
            action=SyncQueue.Action.CREATE,
            status=status,
            payload={"party_name": "Sync Test"},
            processed_at=past_dt if status != SyncQueue.Status.PENDING else None,
        )
        SyncQueue.objects.filter(pk=item.pk).update(
            server_timestamp=past_dt,
            processed_at=past_dt if status != SyncQueue.Status.PENDING else None,
        )
        item.refresh_from_db()
        return item

    def test_purge_old_processed_sync_queue_items(self):
        """Processed SyncQueue items older than 30 days are deleted when call_command('purge_sync_queue', days=30) runs."""
        old_processed = self._create_queue_item(
            "old-proc-45d", SyncQueue.Status.PROCESSED, days_ago=45
        )

        call_command("purge_sync_queue", days=30)

        assert not SyncQueue.objects.filter(pk=old_processed.pk).exists()

    def test_preserve_recent_processed_sync_queue_items(self):
        """Processed SyncQueue items newer than 30 days are preserved."""
        recent_processed = self._create_queue_item(
            "recent-proc-10d", SyncQueue.Status.PROCESSED, days_ago=10
        )
        old_processed = self._create_queue_item(
            "old-proc-40d", SyncQueue.Status.PROCESSED, days_ago=40
        )

        call_command("purge_sync_queue", days=30)

        assert SyncQueue.objects.filter(pk=recent_processed.pk).exists()
        assert not SyncQueue.objects.filter(pk=old_processed.pk).exists()

    def test_pending_sync_queue_items_never_deleted(self):
        """Pending SyncQueue items (status='pending') older than 30 days are NEVER deleted."""
        old_pending = self._create_queue_item(
            "old-pending-60d", SyncQueue.Status.PENDING, days_ago=60
        )

        call_command("purge_sync_queue", days=30)
        assert SyncQueue.objects.filter(pk=old_pending.pk).exists()

        call_command("purge_sync_queue", days=30, include_failed=True)
        assert SyncQueue.objects.filter(pk=old_pending.pk).exists()

    def test_failed_sync_queue_items_preserved_unless_include_failed(self):
        """Failed SyncQueue items older than 30 days are preserved by default, and deleted only when --include-failed is passed."""
        old_failed = self._create_queue_item("old-failed-50d", SyncQueue.Status.FAILED, days_ago=50)

        # Default run without --include-failed preserves failed items
        call_command("purge_sync_queue", days=30)
        assert SyncQueue.objects.filter(pk=old_failed.pk).exists()

        # Run with --include-failed deletes old failed items
        call_command("purge_sync_queue", days=30, include_failed=True)
        assert not SyncQueue.objects.filter(pk=old_failed.pk).exists()


# ===========================================================================
# 3. Database Backup & Data Export (backup_db command & views)
# ===========================================================================
@pytest.mark.django_db
class TestBackupsAndDataExport:
    """Tests for backup_db management command and backup/export settings views."""

    BACKUPS_URL = "/en/settings/backups/"
    DOWNLOAD_JSON_URL = "/en/settings/backups/download-json/"
    DOWNLOAD_CSV_URL = "/en/settings/backups/download-csv/"
    CREATE_BACKUP_URL = "/en/settings/backups/create/"

    def test_backup_db_command_creates_valid_json_file(self, tmp_path, superadmin_user):
        """call_command('backup_db', output_dir=str(tmp_path), retention_days=30) creates a backup_*.json file with required keys."""
        ShopProfile.get_solo()
        Category.objects.create(name="Backup Category", color="#10B981")
        Unit.objects.create(name="Backup Piece", code="bpcs")
        party = Party.objects.create(name="Backup Vendor", party_type=Party.PartyType.VENDOR)
        bill = Bill.objects.create(
            party=party,
            bill_type=Bill.BillType.PURCHASE,
            invoice_no="BKP-INV-01",
            grand_total=Decimal("500.00"),
            created_by=superadmin_user,
        )
        BillItem.objects.create(
            bill=bill,
            serial_no=1,
            item_name="Backup Item",
            quantity=Decimal("1"),
            unit="bpcs",
            unit_price=Decimal("500.00"),
            line_total=Decimal("500.00"),
        )
        Payment.objects.create(
            party=party,
            bill=bill,
            amount=Decimal("200.00"),
            payment_method="cash",
        )

        call_command("backup_db", output_dir=str(tmp_path), retention_days=30)

        backup_files = list(tmp_path.glob("backup_*.json"))
        assert len(backup_files) == 1, "Expected one backup_*.json file to be created."

        data = json.loads(backup_files[0].read_text(encoding="utf-8"))
        expected_keys = {"shop_profile", "categories", "units", "parties", "bills", "payments"}
        assert expected_keys.issubset(set(data.keys()))

    def test_backup_db_command_prunes_expired_backups(self, tmp_path):
        """Old backup_*.json files in output_dir with mtime older than retention_days are automatically pruned."""
        old_backup = tmp_path / "backup_20250101_000000.json"
        old_backup.write_text('{"old": true}', encoding="utf-8")
        # Set mtime to 45 days ago
        old_mtime = time.time() - (45 * 86400)
        os.utime(old_backup, (old_mtime, old_mtime))

        recent_backup = tmp_path / "backup_recent_keep.json"
        recent_backup.write_text('{"recent": true}', encoding="utf-8")

        call_command("backup_db", output_dir=str(tmp_path), retention_days=30)

        assert (
            not old_backup.exists()
        ), "Expired backup file older than retention_days must be pruned."
        assert recent_backup.exists(), "Recent backup file within retention_days must be kept."

    def test_superadmin_download_json_export_safe_from_secrets(
        self, superadmin_client, superadmin_user
    ):
        """Superadmin GET /en/settings/backups/download-json/ returns JSON attachment and does NOT expose password hashes or SECRET_KEY."""
        ShopProfile.get_solo()
        party = Party.objects.create(name="JSON Export Vendor", party_type=Party.PartyType.VENDOR)
        Bill.objects.create(
            party=party,
            invoice_no="JSON-EXP-001",
            grand_total=Decimal("999.00"),
            created_by=superadmin_user,
        )

        response = superadmin_client.get(self.DOWNLOAD_JSON_URL)
        assert response.status_code == 200
        assert "application/json" in response["Content-Type"]
        assert "attachment" in response.get("Content-Disposition", "")

        raw_text = response.content.decode("utf-8")
        data = json.loads(raw_text)

        expected_keys = {"shop_profile", "categories", "units", "parties", "bills", "payments"}
        assert expected_keys.issubset(set(data.keys()))

        # Security check: must never leak password hashes or SECRET_KEY
        assert superadmin_user.password not in raw_text
        assert "pbkdf2_" not in raw_text
        assert settings.SECRET_KEY not in raw_text

    def test_superadmin_download_csv_export_contains_active_bills(
        self, superadmin_client, superadmin_user
    ):
        """Superadmin GET /en/settings/backups/download-csv/ returns text/csv attachment containing active bills only."""
        party = Party.objects.create(name="CSV Export Vendor", party_type=Party.PartyType.VENDOR)
        Bill.objects.create(
            party=party,
            invoice_no="CSV-ACTIVE-101",
            grand_total=Decimal("1250.00"),
            created_by=superadmin_user,
            is_deleted=False,
        )
        Bill.all_objects.create(
            party=party,
            invoice_no="CSV-DELETED-999",
            grand_total=Decimal("800.00"),
            created_by=superadmin_user,
            is_deleted=True,
        )

        response = superadmin_client.get(self.DOWNLOAD_CSV_URL)
        assert response.status_code == 200
        assert "text/csv" in response["Content-Type"]
        assert "attachment" in response.get("Content-Disposition", "")

        csv_text = response.content.decode("utf-8")
        assert "CSV-ACTIVE-101" in csv_text
        assert "CSV-DELETED-999" not in csv_text

    def test_superadmin_post_create_backup_redirects(
        self, superadmin_client, tmp_path, monkeypatch
    ):
        """Superadmin POST /en/settings/backups/create/ creates a backup and redirects."""
        monkeypatch.setattr(settings, "BACKUP_DIR", tmp_path, raising=False)
        response = superadmin_client.post(self.CREATE_BACKUP_URL)
        assert response.status_code in (200, 302)

    def test_backups_endpoints_forbidden_for_unpermitted_staff(self, staff_client):
        """Staff without can_manage_shop receives HTTP 403 on all backup and export endpoints."""
        for url in (
            self.BACKUPS_URL,
            self.DOWNLOAD_JSON_URL,
            self.DOWNLOAD_CSV_URL,
        ):
            res = staff_client.get(url)
            assert res.status_code == 403, f"Expected 403 for GET {url}, got {res.status_code}"

        res_post = staff_client.post(self.CREATE_BACKUP_URL)
        assert res_post.status_code == 403


# ===========================================================================
# 4. Global Search (/en/search/)
# ===========================================================================
@pytest.mark.django_db
class TestGlobalSearch:
    """Tests for Global Search (/en/search/) across Bills, Parties, and BillItems."""

    SEARCH_URL = "/en/search/"

    def test_search_finds_matching_active_bill_by_invoice_no(self, staff_client, staff_user):
        """Searching /en/search/?q=<invoice_no> finds matching active Bill."""
        party = Party.objects.create(name="Search Vendor", party_type=Party.PartyType.VENDOR)
        Bill.objects.create(
            party=party,
            invoice_no="SRCH-INV-7788",
            grand_total=Decimal("3400.00"),
            created_by=staff_user,
        )

        response = staff_client.get(f"{self.SEARCH_URL}?q=SRCH-INV-7788")
        assert response.status_code == 200
        assert "SRCH-INV-7788" in response.content.decode("utf-8")

    def test_search_finds_matching_active_party_by_name(self, staff_client):
        """Searching /en/search/?q=<party_name> finds matching active Party."""
        Party.objects.create(
            name="Zeeshan Mega Wholesale",
            phone="03005551234",
            party_type=Party.PartyType.VENDOR,
        )

        response = staff_client.get(f"{self.SEARCH_URL}?q=Zeeshan+Mega")
        assert response.status_code == 200
        assert "Zeeshan Mega Wholesale" in response.content.decode("utf-8")

    def test_search_finds_matching_bill_item_by_item_name(self, staff_client, staff_user):
        """Searching /en/search/?q=<item_name> finds matching BillItem."""
        party = Party.objects.create(name="Item Search Vendor", party_type=Party.PartyType.VENDOR)
        bill = Bill.objects.create(
            party=party,
            invoice_no="ITEM-SRCH-01",
            grand_total=Decimal("900.00"),
            created_by=staff_user,
        )
        BillItem.objects.create(
            bill=bill,
            serial_no=1,
            item_name="Himalayan Pink Salt 1kg",
            quantity=Decimal("2"),
            unit="kg",
            unit_price=Decimal("450.00"),
            line_total=Decimal("900.00"),
        )

        response = staff_client.get(f"{self.SEARCH_URL}?q=Himalayan+Pink+Salt")
        assert response.status_code == 200
        assert "Himalayan Pink Salt 1kg" in response.content.decode("utf-8")

    def test_soft_deleted_bills_never_appear_in_global_search(self, staff_client, staff_user):
        """Soft-deleted bills (is_deleted=True) NEVER appear in global search results."""
        party = Party.objects.create(name="Trash Search Vendor", party_type=Party.PartyType.VENDOR)
        deleted_bill = Bill.all_objects.create(
            party=party,
            invoice_no="TRASHED-INV-404",
            grand_total=Decimal("5000.00"),
            created_by=staff_user,
            is_deleted=True,
            deleted_at=timezone.now(),
        )
        BillItem.objects.create(
            bill=deleted_bill,
            serial_no=1,
            item_name="SecretDeletedItem99",
            quantity=Decimal("1"),
            unit="pcs",
            unit_price=Decimal("5000.00"),
            line_total=Decimal("5000.00"),
        )

        res_inv = staff_client.get(f"{self.SEARCH_URL}?q=TRASHED-INV-404")
        assert res_inv.status_code == 200
        assert "TRASHED-INV-404" not in res_inv.content.decode("utf-8")

        res_item = staff_client.get(f"{self.SEARCH_URL}?q=SecretDeletedItem99")
        assert res_item.status_code == 200
        assert "SecretDeletedItem99" not in res_item.content.decode("utf-8")

    def test_empty_search_query_returns_200_with_zero_results(self, staff_client):
        """Empty search /en/search/?q= returns HTTP 200 with 0 results cleanly."""
        response = staff_client.get(f"{self.SEARCH_URL}?q=")
        assert response.status_code == 200
        if response.context and "total_results" in response.context:
            assert response.context["total_results"] == 0

    def test_unauthenticated_user_redirected_on_global_search(self, client):
        """Unauthenticated user visiting /en/search/?q=test is redirected to login."""
        response = client.get(f"{self.SEARCH_URL}?q=test")
        assert response.status_code == 302
        assert "/login" in response.url or "/accounts/login" in response.url


# ===========================================================================
# 5. Security Headers & Offline Delta Sync
# ===========================================================================
@pytest.mark.django_db
class TestSecurityHeadersAndOfflineDeltaSync:
    """Tests for HTTP security headers and offline delta sync (?since= / last_pulled_at)."""

    def test_security_headers_present_on_responses(self, staff_client):
        """Responses include X-Content-Type-Options: nosniff and X-Frame-Options: DENY."""
        response = staff_client.get("/en/")
        assert response.status_code == 200
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_offline_sync_js_supports_delta_pull_since_param(self):
        """static/js/offline-sync.js supports last_pulled_at / ?since= parameter for delta pulling."""
        js_path = Path(settings.BASE_DIR) / "static" / "js" / "offline-sync.js"
        assert js_path.exists(), "static/js/offline-sync.js does not exist."
        content = js_path.read_text(encoding="utf-8")
        assert (
            "last_pulled_at" in content
        ), "offline-sync.js must track last_pulled_at for delta sync."
        assert (
            "since=" in content
        ), "offline-sync.js must pass ?since= query parameter to /sync/pull/."
