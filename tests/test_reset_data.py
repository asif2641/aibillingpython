"""tests/test_reset_data.py
===========================
Tests for the factory App Data Reset feature in settings_app.
Verifies permission restriction (superadmin only), confirmation safety,
complete database purge, category/unit re-seeding, and file cleanup.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from bills.models import Bill, BillItem
from categories.models import Category, Unit
from ledger.models import Payment
from parties.models import Party
from scanning.models import BillFile, ScanJob
from settings_app.models import ActivityLog, ShopProfile
from sync.models import SyncQueue

User = get_user_model()


@pytest.fixture
def superadmin_user(db):
    """Create a superadmin user."""
    return User.objects.create_user(
        username="superadmin_test",
        email="superadmin@example.com",
        password="TestPassword123!",
        role=User.Role.SUPERADMIN,
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def staff_user(db):
    """Create a regular staff user without superadmin privileges."""
    return User.objects.create_user(
        username="staff_regular",
        email="staff@example.com",
        password="TestPassword123!",
        role=User.Role.STAFF,
        can_manage_shop=True,
    )


@pytest.fixture
def sample_business_data(db, superadmin_user):
    """Create realistic sample business data across all modules."""
    # Party
    party = Party.objects.create(
        name="Al-Madina Traders",
        phone="03001234567",
        party_type=Party.PartyType.VENDOR,
    )

    # Category
    category, _ = Category.objects.get_or_create(name="Beverages", defaults={"color": "#3B82F6"})

    # Bill
    bill = Bill.all_objects.create(
        party=party,
        invoice_no="INV-999",
        category=category,
        subtotal=Decimal("500.00"),
        grand_total=Decimal("500.00"),
        created_by=superadmin_user,
    )

    # BillItem
    BillItem.objects.create(
        bill=bill,
        item_name="Mineral Water",
        quantity=Decimal("10"),
        unit_price=Decimal("50.00"),
        line_total=Decimal("500.00"),
    )

    # Soft-deleted bill
    Bill.all_objects.create(
        party=party,
        invoice_no="INV-OLD",
        subtotal=Decimal("100.00"),
        grand_total=Decimal("100.00"),
        is_deleted=True,
    )

    # Payment
    Payment.objects.create(
        party=party,
        bill=bill,
        amount=Decimal("500.00"),
        created_by=superadmin_user,
    )

    # ScanJob & File
    scan = ScanJob.objects.create(
        bill=bill,
        status=ScanJob.Status.COMPLETED,
        created_by=superadmin_user,
    )
    BillFile.objects.create(
        bill=bill,
        scan_job=scan,
        file="bills/dummy.png",
        page_number=1,
    )

    # Sync Queue
    SyncQueue.objects.create(
        client_id="uuid-test-1234",
        record_type=SyncQueue.RecordType.BILL,
        action=SyncQueue.Action.CREATE,
    )

    # Activity Log
    ActivityLog.objects.create(
        user=superadmin_user,
        action="bill_created",
        description="Sample bill created",
    )

    # Custom Shop Profile
    profile = ShopProfile.get_solo()
    profile.name = "Custom Store 123"
    profile.phone = "03119876543"
    profile.save()

    return party, bill


@pytest.mark.django_db
class TestResetDataSecurity:
    """Security tests ensuring only Super Admins can access or execute reset."""

    def test_anonymous_user_redirected_to_login(self, client):
        """Anonymous user cannot access reset data view."""
        response = client.get(reverse("reset_data"))
        assert response.status_code == 302
        assert "login" in response.url

    def test_staff_user_is_forbidden(self, client, staff_user):
        """Staff user even with can_manage_shop receives HTTP 403 Forbidden."""
        client.force_login(staff_user)
        response = client.get(reverse("reset_data"))
        assert response.status_code == 403

        # POST is also forbidden
        post_response = client.post(reverse("reset_data"), {"confirm_code": "RESET"})
        assert post_response.status_code == 403

    def test_superadmin_can_access_page(self, client, superadmin_user, sample_business_data):
        """Superadmin receives HTTP 200 with summary counts and confirmation form."""
        client.force_login(superadmin_user)
        response = client.get(reverse("reset_data"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Danger Zone: Factory App Data Reset" in content
        assert "RESET" in content
        assert reverse("reset_data") in content


@pytest.mark.django_db
class TestResetDataExecution:
    """Execution tests verifying validation, data purging, and factory state."""

    def test_invalid_confirmation_code_rejected(
        self, client, superadmin_user, sample_business_data
    ):
        """Typing anything other than 'RESET' returns 400 and does NOT wipe data."""
        client.force_login(superadmin_user)

        response = client.post(reverse("reset_data"), {"confirm_code": "reset"})
        assert response.status_code == 400

        # Verify nothing was deleted
        assert Bill.all_objects.count() >= 2
        assert Party.objects.count() >= 1
        assert Payment.objects.count() >= 1

    def test_factory_reset_wipes_all_business_data(
        self, client, superadmin_user, sample_business_data
    ):
        """Typing 'RESET' wipes bills, parties, payments, scans, and resets profile."""
        client.force_login(superadmin_user)

        response = client.post(reverse("reset_data"), {"confirm_code": "RESET"})
        assert response.status_code == 302
        assert response.url == reverse("shop_profile")

        # Verify all financial & scanning records are 0
        assert Bill.all_objects.count() == 0
        assert BillItem.objects.count() == 0
        assert Payment.objects.count() == 0
        assert Party.objects.count() == 0
        assert ScanJob.objects.count() == 0
        assert BillFile.objects.count() == 0
        assert SyncQueue.objects.count() == 0

        # Verify default categories and units are re-seeded
        assert Category.objects.count() >= 10
        assert Unit.objects.count() >= 9

        # Verify shop profile is reset to factory default
        profile = ShopProfile.get_solo()
        assert profile.name == "My Shop"
        assert profile.phone == ""

        # Verify superadmin user still exists and is logged in
        assert User.objects.filter(pk=superadmin_user.pk).exists()

        # Verify activity log recorded the system reset
        assert ActivityLog.objects.filter(action="system_reset").exists()

    def test_factory_reset_with_staff_removal(
        self, client, superadmin_user, staff_user, sample_business_data
    ):
        """Optionally selecting reset_staff removes other accounts, keeps superadmin."""
        client.force_login(superadmin_user)

        # Before reset, both users exist
        assert User.objects.count() >= 2

        response = client.post(
            reverse("reset_data"),
            {"confirm_code": "RESET", "reset_staff": "on"},
        )
        assert response.status_code == 302

        # Staff user is removed, superadmin is preserved
        assert not User.objects.filter(pk=staff_user.pk).exists()
        assert User.objects.filter(pk=superadmin_user.pk).exists()
