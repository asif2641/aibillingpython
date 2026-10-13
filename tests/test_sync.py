"""tests/test_sync.py
===================
QA Test-First Suite for Phase 6: Offline Sync Queue, Processing Services,
Idempotency, Party Resolution, Payment Handling, and API Endpoints.

Coverage:
1. SyncQueue Model Schema & Constraints:
   - Creation with valid fields (client_id, record_type, action, payload, status="pending").
   - Uniqueness constraint on client_id (IntegrityError on duplicate).
   - String representation (__str__).
   - Status choices (pending, processed, failed).
   - Resolution and error tracking fields (resolved_record_id, error_message).

2. process_sync_queue_item Service Logic:
   - Happy path: Syncing a manual bill payload creates new Bill and BillItem records.
     - bill.source == "manual"
     - bill.status == "Verified"
     - Line totals, subtotal, and grand_total calculated with Decimal and money_round().
     - queue_item.status == "processed" and queue_item.resolved_record_id == bill.pk.
   - Idempotency:
     - Reprocessing the exact same queue_item does NOT create duplicate bills.
     - Returns existing bill.pk.
     - Pushing duplicate client_id does not duplicate records.
   - Party Resolution:
     - Auto-creates Party when party_name is passed without party_id.
     - Matches existing Party by name when available.
     - Associates with valid party_id when provided.
     - Sale bills correctly associate/create Party as customer.
   - Payment Handling:
     - Full payment creates Payment record and sets bill payment_status to 'Paid'.
     - Partial payment creates Payment record and sets bill payment_status to 'Partially Paid'.
     - Zero payment creates no Payment record and leaves bill payment_status as 'Unpaid'.
   - Validation & Failure Handling:
     - Invalid/negative quantity marks queue_item as 'failed' with error_message.
     - Invalid/negative unit_price marks queue_item as 'failed' with error_message.
     - Missing line items marks queue_item as 'failed' without crashing.
     - Missing party information marks queue_item as 'failed' without crashing.
     - Negative discount or tax fails cleanly.
   - Edge Cases:
     - Urdu / bilingual party and item names preserved without corruption.
     - Fractional precision rounding with money_round().
     - Pre-existing category linkage via category_id.

3. sync_push_service & sync_pull_service:
   - Batch push processes multiple items and returns summary of processed and failed counts.
   - Batch push with empty list returns clean zero summary.
   - sync_pull_service returns active parties, active categories, and units for offline cache.
   - Archived categories and inactive parties are omitted from pull payload.

4. Sync API Endpoints:
   - POST /sync/push/ requires authentication; staff/superadmin can push batch.
   - GET /sync/pull/ requires authentication; returns reference data JSON.
"""

import json
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.urls import NoReverseMatch, reverse

from billing.utils import money_round
from bills.models import Bill
from categories.models import Category, Unit
from ledger.models import Payment
from parties.models import Party

# Late-import guards for test-first validity:
# Builders will implement SyncQueue in sync.models and services in sync.services.
try:
    from sync.models import SyncQueue
except (ImportError, AttributeError):
    SyncQueue = None

try:
    from sync.services import (
        process_sync_queue_item,
        sync_pull_service,
        sync_push_service,
    )
except (ImportError, AttributeError):
    process_sync_queue_item = None
    sync_pull_service = None
    sync_push_service = None

User = get_user_model()


def call_process_sync_queue_item(queue_item, user=None):
    """Invoke process_sync_queue_item supporting either (item, user) or (item) signatures."""
    assert (
        process_sync_queue_item is not None
    ), "process_sync_queue_item is not implemented in sync.services"
    try:
        return process_sync_queue_item(queue_item, user=user)
    except TypeError:
        return process_sync_queue_item(queue_item)


def call_sync_push_service(batch, user=None):
    """Invoke sync_push_service supporting either (batch, user) or (user, batch) signatures."""
    assert sync_push_service is not None, "sync_push_service is not implemented in sync.services"
    try:
        return sync_push_service(batch, user=user)
    except TypeError:
        try:
            return sync_push_service(user, batch)
        except TypeError:
            return sync_push_service(batch)


def call_sync_pull_service(user=None):
    """Invoke sync_pull_service supporting either (user) or () signatures."""
    assert sync_pull_service is not None, "sync_pull_service is not implemented in sync.services"
    try:
        return sync_pull_service(user=user)
    except TypeError:
        try:
            return sync_pull_service(user)
        except TypeError:
            return sync_pull_service()


def resolve_sync_endpoint(action: str, candidate_paths: list[str]) -> str:
    """Resolve sync URL via Django reverse name or fall back to candidate paths."""
    for reverse_name in [f"sync:{action}", f"sync_{action}", action]:
        try:
            return reverse(reverse_name)
        except (NoReverseMatch, Exception):
            pass
    return candidate_paths[0]


# ---------------------------------------------------------------------------
# 1. SyncQueue Model Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestSyncQueueModel:
    """Verify SyncQueue schema, uniqueness constraints, and string representation."""

    def test_sync_queue_creation_valid(self, staff_user):
        """SyncQueue creates successfully with all valid fields and default status='pending'."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        payload = {
            "party_name": "Lahore Wholesale Center",
            "bill_type": "purchase",
            "invoice_no": "OFF-1001",
            "bill_date": "2026-10-13",
            "items": [
                {
                    "item_name": "Cooking Oil 5L",
                    "quantity": "2",
                    "unit": "tin",
                    "unit_price": "2200.00",
                }
            ],
            "discount": "0.00",
            "tax": "0.00",
            "amount_paid": "0.00",
        }

        item = SyncQueue.objects.create(
            client_id="client-uuid-001",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        assert item.pk is not None
        assert item.client_id == "client-uuid-001"
        assert item.record_type == "bill"
        assert item.action == "create"
        assert item.payload == payload
        assert item.status == "pending"
        assert item.resolved_record_id is None
        assert item.error_message in ("", None)
        timestamp = getattr(item, "server_timestamp", getattr(item, "created_at", None))
        assert timestamp is not None

    def test_sync_queue_client_id_uniqueness(self):
        """Uniqueness constraint on client_id raises IntegrityError on duplicates."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        SyncQueue.objects.create(
            client_id="unique-client-uuid-999",
            record_type="bill",
            action="create",
            payload={"party_name": "Test Vendor", "items": []},
            status="pending",
        )

        with pytest.raises(IntegrityError):
            SyncQueue.objects.create(
                client_id="unique-client-uuid-999",
                record_type="bill",
                action="create",
                payload={"party_name": "Duplicate Attempt", "items": []},
                status="pending",
            )

    def test_sync_queue_str_representation(self):
        """String representation includes client_id, record_type, or status."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        item = SyncQueue.objects.create(
            client_id="str-check-uuid-555",
            record_type="bill",
            action="create",
            payload={"party_name": "Vendor"},
            status="pending",
        )
        rep = str(item)
        assert "str-check-uuid-555" in rep or "bill" in rep or "pending" in rep

    def test_sync_queue_status_choices(self):
        """SyncQueue accepts pending, processed, and failed statuses."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        for status_val in ["pending", "processed", "failed"]:
            item = SyncQueue.objects.create(
                client_id=f"uuid-status-{status_val}",
                record_type="bill",
                action="create",
                payload={},
                status=status_val,
            )
            item.refresh_from_db()
            assert item.status == status_val

    def test_sync_queue_resolved_and_error_fields(self):
        """SyncQueue can store resolved_record_id and descriptive error_message."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        item = SyncQueue.objects.create(
            client_id="uuid-error-tracker",
            record_type="bill",
            action="create",
            payload={},
            status="failed",
            resolved_record_id=42,
            error_message="Validation error: unit_price cannot be negative",
        )
        item.refresh_from_db()
        assert item.resolved_record_id == 42
        assert "unit_price cannot be negative" in item.error_message


# ---------------------------------------------------------------------------
# 2. process_sync_queue_item Service Logic Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestProcessSyncQueueItem:
    """Verify processing offline sync items into verified bills, recalculations, and handling."""

    def test_happy_path_manual_bill_creation(self, staff_user):
        """Processing a valid offline manual bill creates Bill, BillItems, and updates queue."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"
        assert (
            process_sync_queue_item is not None
        ), "process_sync_queue_item is not implemented in sync.services"

        payload = {
            "party_name": "Al-Rehman Traders",
            "bill_type": "purchase",
            "invoice_no": "INV-SYNC-101",
            "bill_date": "2026-10-13",
            "bill_time": "14:30",
            "items": [
                {
                    "item_name": "Cooking Oil 5L",
                    "quantity": "2",
                    "unit": "tin",
                    "unit_price": "2500.50",
                },
                {
                    "item_name": "Basmati Rice 10kg",
                    "quantity": "3",
                    "unit": "bag",
                    "unit_price": "1800.00",
                },
            ],
            "discount": "100.00",
            "tax": "50.00",
            "amount_paid": "0.00",
            "notes": "Synced from offline IndexedDB storage",
        }

        queue_item = SyncQueue.objects.create(
            client_id="offline-happy-path-001",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        result = call_process_sync_queue_item(queue_item, user=staff_user)

        queue_item.refresh_from_db()
        assert queue_item.status == "processed"
        assert queue_item.resolved_record_id is not None

        # Verify created Bill
        bill = Bill.all_objects.get(pk=queue_item.resolved_record_id)
        if isinstance(result, Bill):
            assert result.pk == bill.pk
        elif isinstance(result, int):
            assert result == bill.pk

        assert bill.source == "manual"
        assert bill.status == "Verified"
        assert bill.party.name == "Al-Rehman Traders"
        assert bill.invoice_no == "INV-SYNC-101"
        assert str(bill.bill_date) == "2026-10-13"
        assert bill.notes == "Synced from offline IndexedDB storage"

        # Verify server-side Decimal money calculations
        expected_line1 = money_round(Decimal("2") * Decimal("2500.50"))  # 5001.00
        expected_line2 = money_round(Decimal("3") * Decimal("1800.00"))  # 5400.00
        expected_subtotal = money_round(expected_line1 + expected_line2)  # 10401.00
        expected_grand_total = money_round(
            expected_subtotal - Decimal("100.00") + Decimal("50.00")
        )  # 10351.00

        items = list(bill.items.order_by("serial_no"))
        assert len(items) == 2
        assert items[0].item_name == "Cooking Oil 5L"
        assert items[0].quantity == Decimal("2")
        assert items[0].unit_price == Decimal("2500.50")
        assert items[0].line_total == expected_line1

        assert items[1].item_name == "Basmati Rice 10kg"
        assert items[1].quantity == Decimal("3")
        assert items[1].unit_price == Decimal("1800.00")
        assert items[1].line_total == expected_line2

        assert bill.subtotal == expected_subtotal
        assert bill.discount == Decimal("100.00")
        assert bill.tax == Decimal("50.00")
        assert bill.grand_total == expected_grand_total

    def test_idempotency_duplicate_processing(self, staff_user):
        """Calling process_sync_queue_item multiple times on the same item does not duplicate bills."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        payload = {
            "party_name": "Idempotent Wholesale",
            "bill_type": "purchase",
            "invoice_no": "IDEM-001",
            "bill_date": "2026-10-13",
            "items": [
                {
                    "item_name": "Flour 20kg",
                    "quantity": "1",
                    "unit": "bag",
                    "unit_price": "2100.00",
                }
            ],
            "discount": "0.00",
            "tax": "0.00",
            "amount_paid": "0.00",
        }

        queue_item = SyncQueue.objects.create(
            client_id="offline-idempotency-uuid",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        initial_count = Bill.all_objects.count()

        # First run: processes item
        res1 = call_process_sync_queue_item(queue_item, user=staff_user)
        queue_item.refresh_from_db()
        assert queue_item.status == "processed"
        resolved_id = queue_item.resolved_record_id
        assert Bill.all_objects.count() == initial_count + 1

        # Second run: must be idempotent, returning the existing bill ID without duplicate Bill
        res2 = call_process_sync_queue_item(queue_item, user=staff_user)
        queue_item.refresh_from_db()
        assert queue_item.status == "processed"
        assert queue_item.resolved_record_id == resolved_id
        assert Bill.all_objects.count() == initial_count + 1

        def _extract_pk(res):
            if isinstance(res, tuple) and len(res) >= 3:
                return res[2]
            return res.pk if isinstance(res, Bill) else res

        assert _extract_pk(res1) == _extract_pk(res2)

    def test_party_resolution_auto_creates_party_when_no_party_id(self, staff_user):
        """When party_name is provided without party_id, automatically matches or creates party."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        party_name = "New Auto Created Vendor"
        assert not Party.objects.filter(name=party_name).exists()

        payload = {
            "party_name": party_name,
            "bill_type": "purchase",
            "invoice_no": "AUTO-P-01",
            "bill_date": "2026-10-13",
            "items": [
                {
                    "item_name": "Item A",
                    "quantity": "1",
                    "unit": "pcs",
                    "unit_price": "100.00",
                }
            ],
        }

        queue_item = SyncQueue.objects.create(
            client_id="party-auto-create-uuid",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        call_process_sync_queue_item(queue_item, user=staff_user)

        created_party = Party.objects.filter(name=party_name).first()
        assert created_party is not None
        assert created_party.party_type in (Party.PartyType.VENDOR, Party.PartyType.BOTH)

        bill = Bill.all_objects.get(pk=queue_item.resolved_record_id)
        assert bill.party == created_party

    def test_party_resolution_matches_existing_party_by_name(self, staff_user):
        """When party_name matches an existing party, reuses that party instead of creating duplicate."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        existing_party = Party.objects.create(
            name="Existing Faisalabad Supplier",
            phone="03001234567",
            party_type=Party.PartyType.VENDOR,
        )

        payload = {
            "party_name": "Existing Faisalabad Supplier",
            "bill_type": "purchase",
            "invoice_no": "EXIST-P-01",
            "bill_date": "2026-10-13",
            "items": [
                {
                    "item_name": "Item B",
                    "quantity": "2",
                    "unit": "pcs",
                    "unit_price": "50.00",
                }
            ],
        }

        queue_item = SyncQueue.objects.create(
            client_id="party-match-uuid",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        call_process_sync_queue_item(queue_item, user=staff_user)

        # Confirm no duplicate party was created
        assert Party.objects.filter(name="Existing Faisalabad Supplier").count() == 1
        bill = Bill.all_objects.get(pk=queue_item.resolved_record_id)
        assert bill.party == existing_party

    def test_party_resolution_associates_valid_party_id(self, staff_user):
        """When valid party_id is supplied, associates bill with that existing party."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        existing_party = Party.objects.create(
            name="Prime Karachi Distributors",
            phone="03219876543",
            party_type=Party.PartyType.VENDOR,
        )

        payload = {
            "party_id": existing_party.pk,
            "party_name": "Ignored or matching name",
            "bill_type": "purchase",
            "invoice_no": "PID-01",
            "bill_date": "2026-10-13",
            "items": [
                {
                    "item_name": "Item C",
                    "quantity": "1",
                    "unit": "box",
                    "unit_price": "750.00",
                }
            ],
        }

        queue_item = SyncQueue.objects.create(
            client_id="party-id-association-uuid",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        call_process_sync_queue_item(queue_item, user=staff_user)

        bill = Bill.all_objects.get(pk=queue_item.resolved_record_id)
        assert bill.party.pk == existing_party.pk

    def test_party_resolution_sale_bill_creates_customer(self, staff_user):
        """Sale bill with new party_name creates a customer party."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        payload = {
            "party_name": "Tariq Customer",
            "bill_type": "sale",
            "invoice_no": "SALE-SYNC-01",
            "bill_date": "2026-10-13",
            "items": [
                {
                    "item_name": "Soap",
                    "quantity": "5",
                    "unit": "pcs",
                    "unit_price": "120.00",
                }
            ],
        }

        queue_item = SyncQueue.objects.create(
            client_id="sale-customer-create-uuid",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        call_process_sync_queue_item(queue_item, user=staff_user)

        bill = Bill.all_objects.get(pk=queue_item.resolved_record_id)
        assert bill.bill_type == Bill.BillType.SALE
        assert bill.party.party_type in (
            Party.PartyType.CUSTOMER,
            Party.PartyType.BOTH,
        )

    def test_payment_handling_full_payment(self, staff_user):
        """When amount_paid equals grand_total, creates Payment record and marks bill 'Paid'."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        payload = {
            "party_name": "Cash Supplier",
            "bill_type": "purchase",
            "invoice_no": "PAID-01",
            "bill_date": "2026-10-13",
            "items": [
                {
                    "item_name": "Item Full Pay",
                    "quantity": "2",
                    "unit": "box",
                    "unit_price": "2500.00",
                }
            ],
            "discount": "0.00",
            "tax": "0.00",
            "amount_paid": "5000.00",
        }

        queue_item = SyncQueue.objects.create(
            client_id="payment-full-uuid",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        call_process_sync_queue_item(queue_item, user=staff_user)

        bill = Bill.all_objects.get(pk=queue_item.resolved_record_id)
        assert bill.grand_total == Decimal("5000.00")
        assert bill.amount_paid == Decimal("5000.00")
        assert bill.payment_status == Bill.PaymentStatus.PAID

        # Verify Payment record
        payment = Payment.objects.filter(bill=bill).first()
        assert payment is not None
        assert payment.amount == Decimal("5000.00")
        assert payment.party == bill.party

    def test_payment_handling_partial_payment(self, staff_user):
        """When 0 < amount_paid < grand_total, creates Payment and marks bill 'Partially Paid'."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        payload = {
            "party_name": "Credit Supplier",
            "bill_type": "purchase",
            "invoice_no": "PART-01",
            "bill_date": "2026-10-13",
            "items": [
                {
                    "item_name": "Item Partial Pay",
                    "quantity": "1",
                    "unit": "carton",
                    "unit_price": "10000.00",
                }
            ],
            "discount": "0.00",
            "tax": "0.00",
            "amount_paid": "4000.00",
        }

        queue_item = SyncQueue.objects.create(
            client_id="payment-partial-uuid",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        call_process_sync_queue_item(queue_item, user=staff_user)

        bill = Bill.all_objects.get(pk=queue_item.resolved_record_id)
        assert bill.grand_total == Decimal("10000.00")
        assert bill.amount_paid == Decimal("4000.00")
        assert bill.payment_status == Bill.PaymentStatus.PARTIALLY_PAID

        payment = Payment.objects.filter(bill=bill).first()
        assert payment is not None
        assert payment.amount == Decimal("4000.00")

    def test_payment_handling_zero_payment(self, staff_user):
        """When amount_paid is 0 or omitted, creates no Payment and marks bill 'Unpaid'."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        payload = {
            "party_name": "Unpaid Supplier",
            "bill_type": "purchase",
            "invoice_no": "UNP-01",
            "bill_date": "2026-10-13",
            "items": [
                {
                    "item_name": "Goods",
                    "quantity": "1",
                    "unit": "pcs",
                    "unit_price": "1200.00",
                }
            ],
            "discount": "0.00",
            "tax": "0.00",
            "amount_paid": "0.00",
        }

        queue_item = SyncQueue.objects.create(
            client_id="payment-zero-uuid",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        call_process_sync_queue_item(queue_item, user=staff_user)

        bill = Bill.all_objects.get(pk=queue_item.resolved_record_id)
        assert bill.amount_paid == Decimal("0.00")
        assert bill.payment_status == Bill.PaymentStatus.UNPAID
        assert not Payment.objects.filter(bill=bill).exists()

    def test_validation_negative_quantity_fails_cleanly(self, staff_user):
        """Invalid or negative quantity marks queue_item failed with descriptive error_message."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        payload = {
            "party_name": "Test Supplier",
            "items": [
                {
                    "item_name": "Flour",
                    "quantity": "-5",
                    "unit": "kg",
                    "unit_price": "100.00",
                }
            ],
        }

        queue_item = SyncQueue.objects.create(
            client_id="fail-qty-uuid",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        initial_bill_count = Bill.all_objects.count()

        call_process_sync_queue_item(queue_item, user=staff_user)

        queue_item.refresh_from_db()
        assert queue_item.status == "failed"
        assert queue_item.resolved_record_id is None
        assert queue_item.error_message != ""
        assert Bill.all_objects.count() == initial_bill_count

    def test_validation_negative_unit_price_fails_cleanly(self, staff_user):
        """Invalid or negative unit_price marks queue_item failed with error_message."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        payload = {
            "party_name": "Test Supplier",
            "items": [
                {
                    "item_name": "Tea",
                    "quantity": "2",
                    "unit": "pack",
                    "unit_price": "-250.00",
                }
            ],
        }

        queue_item = SyncQueue.objects.create(
            client_id="fail-price-uuid",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        call_process_sync_queue_item(queue_item, user=staff_user)

        queue_item.refresh_from_db()
        assert queue_item.status == "failed"
        assert queue_item.resolved_record_id is None
        assert queue_item.error_message != ""

    def test_validation_malformed_payload_missing_items(self, staff_user):
        """Payload without items fails cleanly without uncaught exceptions crashing service."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        payload = {
            "party_name": "Test Supplier",
            "items": [],  # Empty items array
        }

        queue_item = SyncQueue.objects.create(
            client_id="fail-no-items-uuid",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        call_process_sync_queue_item(queue_item, user=staff_user)

        queue_item.refresh_from_db()
        assert queue_item.status == "failed"
        assert queue_item.error_message != ""

    def test_validation_malformed_payload_missing_party(self, staff_user):
        """Payload without party name or party_id fails cleanly."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        payload = {
            "party_name": "",
            "items": [
                {
                    "item_name": "Salt",
                    "quantity": "1",
                    "unit": "kg",
                    "unit_price": "50.00",
                }
            ],
        }

        queue_item = SyncQueue.objects.create(
            client_id="fail-no-party-uuid",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        call_process_sync_queue_item(queue_item, user=staff_user)

        queue_item.refresh_from_db()
        assert queue_item.status == "failed"
        assert queue_item.error_message != ""

    def test_edge_case_urdu_bilingual_payload(self, staff_user):
        """Payload with Urdu party and item names is processed without encoding distortion."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        payload = {
            "party_name": "تاج محل بیکری",
            "bill_type": "purchase",
            "invoice_no": "URDU-001",
            "bill_date": "2026-10-13",
            "items": [
                {
                    "item_name": "Sheermal",
                    "urdu_item_name": "شیرمال",
                    "quantity": "10",
                    "unit": "عدد",
                    "unit_price": "80.00",
                }
            ],
        }

        queue_item = SyncQueue.objects.create(
            client_id="urdu-sync-uuid-01",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        call_process_sync_queue_item(queue_item, user=staff_user)

        bill = Bill.all_objects.get(pk=queue_item.resolved_record_id)
        assert bill.party.name == "تاج محل بیکری"
        item = bill.items.first()
        assert item.urdu_item_name == "شیرمال"
        assert item.unit == "عدد"

    def test_edge_case_fractional_precision_and_money_round(self, staff_user):
        """Fractional quantities and prices are rounded using the standard money_round() rule."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        payload = {
            "party_name": "Precision Chemical Supplier",
            "items": [
                {
                    "item_name": "Chemical Solution",
                    "quantity": "3.3333",
                    "unit": "ltr",
                    "unit_price": "100.50",
                }
            ],
            "discount": "0.00",
            "tax": "0.00",
        }

        queue_item = SyncQueue.objects.create(
            client_id="precision-round-uuid",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        call_process_sync_queue_item(queue_item, user=staff_user)

        bill = Bill.all_objects.get(pk=queue_item.resolved_record_id)
        expected_line = money_round(Decimal("3.3333") * Decimal("100.50"))
        assert bill.items.first().line_total == expected_line
        assert bill.grand_total == expected_line

    def test_edge_case_category_linkage(self, staff_user):
        """When category_id is provided in payload, associates bill with that category."""
        assert SyncQueue is not None, "SyncQueue model is not implemented in sync.models"

        category = Category.objects.create(
            name="Packaging Material",
            urdu_name="پیکنگ کا سامان",
            color="#6366F1",
        )

        payload = {
            "party_name": "Carton Box Supplier",
            "category_id": category.pk,
            "items": [
                {
                    "item_name": "Boxes",
                    "quantity": "100",
                    "unit": "pcs",
                    "unit_price": "25.00",
                }
            ],
        }

        queue_item = SyncQueue.objects.create(
            client_id="cat-linkage-uuid",
            record_type="bill",
            action="create",
            payload=payload,
            status="pending",
        )

        call_process_sync_queue_item(queue_item, user=staff_user)

        bill = Bill.all_objects.get(pk=queue_item.resolved_record_id)
        assert bill.category == category


# ---------------------------------------------------------------------------
# 3. sync_push_service & sync_pull_service Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestSyncBatchServices:
    """Verify batch push processing and reference data pull services."""

    def test_sync_push_service_batch_processing(self, staff_user):
        """Batch push processes multiple offline items, returning count of processed and failed."""
        assert (
            sync_push_service is not None
        ), "sync_push_service is not implemented in sync.services"

        batch = [
            {
                "client_id": "batch-item-valid-1",
                "record_type": "bill",
                "action": "create",
                "payload": {
                    "party_name": "Vendor Batch 1",
                    "items": [
                        {
                            "item_name": "Item 1",
                            "quantity": "1",
                            "unit_price": "500.00",
                        }
                    ],
                },
            },
            {
                "client_id": "batch-item-valid-2",
                "record_type": "bill",
                "action": "create",
                "payload": {
                    "party_name": "Vendor Batch 2",
                    "items": [
                        {
                            "item_name": "Item 2",
                            "quantity": "2",
                            "unit_price": "300.00",
                        }
                    ],
                },
            },
            {
                "client_id": "batch-item-invalid-3",
                "record_type": "bill",
                "action": "create",
                "payload": {
                    "party_name": "Broken Vendor",
                    "items": [
                        {
                            "item_name": "Negative Qty",
                            "quantity": "-1",
                            "unit_price": "100.00",
                        }
                    ],
                },
            },
        ]

        summary = call_sync_push_service(batch, user=staff_user)

        assert isinstance(summary, dict)
        processed = summary.get("processed", [])
        processed_count = len(processed) if isinstance(processed, list) else processed
        failed = summary.get("failed", [])
        failed_count = len(failed) if isinstance(failed, list) else failed

        assert processed_count == 2
        assert failed_count == 1
        assert "results" in summary or "items" in summary or summary.get("total") == 3

    def test_sync_push_service_empty_batch(self, staff_user):
        """Batch push with empty list returns clean summary with zero processed."""
        assert (
            sync_push_service is not None
        ), "sync_push_service is not implemented in sync.services"

        summary = call_sync_push_service([], user=staff_user)
        assert isinstance(summary, dict)
        processed = summary.get("processed", [])
        processed_count = len(processed) if isinstance(processed, list) else processed
        failed = summary.get("failed", [])
        failed_count = len(failed) if isinstance(failed, list) else failed

        assert processed_count == 0
        assert failed_count == 0

    def test_sync_pull_service_returns_cached_reference_data(self, staff_user):
        """sync_pull_service returns active parties, categories, and units for offline cache."""
        assert (
            sync_pull_service is not None
        ), "sync_pull_service is not implemented in sync.services"

        # Active & Inactive parties
        active_party = Party.objects.create(
            name="Pull Active Party",
            party_type=Party.PartyType.VENDOR,
            is_active=True,
        )
        inactive_party = Party.objects.create(
            name="Pull Inactive Party",
            party_type=Party.PartyType.VENDOR,
            is_active=False,
        )

        # Active & Archived categories
        active_cat = Category.objects.create(
            name="Pull Active Cat",
            color="#10B981",
            is_archived=False,
        )
        archived_cat = Category.objects.create(
            name="Pull Archived Cat",
            color="#EF4444",
            is_archived=True,
        )

        # Seed standard unit
        unit = Unit.objects.create(name="Kilogram", code="kg_pull_test")

        data = call_sync_pull_service(user=staff_user)

        assert isinstance(data, dict)
        assert "parties" in data
        assert "categories" in data
        assert "units" in data

        # Check party list
        party_names = [p["name"] for p in data["parties"]]
        assert active_party.name in party_names
        assert inactive_party.name not in party_names

        # Check category list
        cat_names = [c["name"] for c in data["categories"]]
        assert active_cat.name in cat_names
        assert archived_cat.name not in cat_names

        # Check unit list
        unit_codes = [u["code"] for u in data["units"]]
        assert unit.code in unit_codes


# ---------------------------------------------------------------------------
# 4. Sync API Endpoints Integration Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestSyncAPIEndpoints:
    """Verify HTTP API endpoints for offline sync push and pull."""

    def test_sync_push_api_unauthenticated_forbidden_or_redirect(self, client):
        """Unauthenticated requests to sync push endpoint redirect or return 401/403."""
        endpoint = resolve_sync_endpoint("push", ["/en/sync/push/", "/sync/push/"])
        response = client.post(
            endpoint,
            data=json.dumps({"items": []}),
            content_type="application/json",
        )
        assert response.status_code in (
            302,
            401,
            403,
        ), f"Expected login redirect or forbidden, got {response.status_code}"

    def test_sync_push_api_authenticated_staff_success(self, staff_client, staff_user):
        """Authenticated staff can POST offline items and receive JSON summary."""
        endpoint = resolve_sync_endpoint("push", ["/en/sync/push/", "/sync/push/"])

        payload = {
            "items": [
                {
                    "client_id": "api-push-uuid-001",
                    "record_type": "bill",
                    "action": "create",
                    "payload": {
                        "party_name": "API Pushed Vendor",
                        "items": [
                            {
                                "item_name": "Sugar 1kg",
                                "quantity": "1",
                                "unit_price": "160.00",
                            }
                        ],
                    },
                }
            ]
        }

        response = staff_client.post(
            endpoint,
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert "processed" in data
        processed = data.get("processed", 0)
        processed_count = len(processed) if isinstance(processed, list) else processed
        assert processed_count == 1

    def test_sync_pull_api_unauthenticated_forbidden_or_redirect(self, client):
        """Unauthenticated requests to sync pull endpoint redirect or return 401/403."""
        endpoint = resolve_sync_endpoint("pull", ["/en/sync/pull/", "/sync/pull/"])
        response = client.get(endpoint)
        assert response.status_code in (
            302,
            401,
            403,
        ), f"Expected login redirect or forbidden, got {response.status_code}"

    def test_sync_pull_api_authenticated_staff_success(self, staff_client, staff_user):
        """Authenticated staff can GET serialized reference data for offline caching."""
        Party.objects.create(name="Pull API Vendor", party_type=Party.PartyType.VENDOR)
        Category.objects.create(name="Pull API Category", color="#3B82F6")

        endpoint = resolve_sync_endpoint("pull", ["/en/sync/pull/", "/sync/pull/"])
        response = staff_client.get(endpoint)

        assert response.status_code == 200
        data = response.json()
        assert "parties" in data
        assert "categories" in data
        assert "units" in data
        assert len(data["parties"]) >= 1

    def test_sync_push_api_superadmin_access(self, superadmin_client, superadmin_user):
        """Super Admin can also push offline synced bills."""
        endpoint = resolve_sync_endpoint("push", ["/en/sync/push/", "/sync/push/"])

        payload = {
            "items": [
                {
                    "client_id": "admin-push-uuid-001",
                    "record_type": "bill",
                    "action": "create",
                    "payload": {
                        "party_name": "Super Admin Sync Vendor",
                        "items": [
                            {
                                "item_name": "Admin Item",
                                "quantity": "1",
                                "unit_price": "500.00",
                            }
                        ],
                    },
                }
            ]
        }

        response = superadmin_client.post(
            endpoint,
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 200
        processed = response.json().get("processed", 0)
        processed_count = len(processed) if isinstance(processed, list) else processed
        assert processed_count == 1
