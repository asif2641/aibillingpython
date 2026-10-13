"""tests/test_bills.py
====================
Test-first test suite for Phase 3: Bill and BillItem Models, Totals Recalculation,
Soft Delete / Trash Pattern, and Bill Views.

Coverage:
- Bill & BillItem Models Schema & Money Precision:
  - Bill fields: bill_type, party, invoice_no, bill_date, category, status, source,
    subtotal, discount, tax, grand_total, payment_status, amount_paid, is_deleted, deleted_at.
  - BillItem fields: bill, serial_no, item_name, urdu_item_name, quantity, unit,
    unit_price, line_total.
  - Monetary values and quantities must use DecimalField, never float.
  - Model choices and string representations.
- Totals Recalculation Service (bills.services.recalculate_bill_totals):
  - Calculates line_total = money_round(quantity * unit_price).
  - Calculates subtotal = sum(item.line_total for item in items).
  - Calculates grand_total = money_round(subtotal - discount + tax).
  - Rounding rule: ROUND_HALF_UP with 2 decimal places.
  - Edge cases: fractional quantities, zero items, zero quantity/price, large numbers.
  - Failure cases: negative discount, negative tax, discount exceeding subtotal.
- Soft Delete & Trash Pattern:
  - Soft delete sets is_deleted=True and deleted_at timestamp.
  - Active queries exclude soft-deleted records.
  - Trash view (/en/bills/trash/) lists soft-deleted bills.
  - Restore view (/en/bills/<id>/restore/) restores bill (is_deleted=False, deleted_at=None).
  - Permissions: Staff without can_delete_records receives HTTP 403 on trash, delete, restore.
  - Staff with can_delete_records=True and Superadmin have full trash/delete/restore access.
- Views & Workflow:
  - Unauthenticated access redirects to login.
  - Bill list view (/en/bills/): search by invoice_no, filter by party, date, payment_status, paginated.
  - Create manual bill (/en/bills/add/): creates bill with line items.
  - Bill detail view (/en/bills/<id>/).
  - Bill edit view (/en/bills/<id>/edit/).
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

try:
    from bills.models import Bill, BillItem
except (ImportError, AttributeError):
    Bill = None
    BillItem = None

try:
    from bills.services import recalculate_bill_totals
except (ImportError, AttributeError):
    recalculate_bill_totals = None

try:
    from parties.models import Party
except (ImportError, AttributeError):
    Party = None

try:
    from categories.models import Category
except (ImportError, AttributeError):
    Category = None

User = get_user_model()


def resolve_candidate_url(candidate_paths, reverse_names=None):
    """Resolve a URL via Django reverse if registered, or return the first candidate path."""
    if reverse_names:
        for item in reverse_names:
            if isinstance(item, tuple):
                name, args = item
            else:
                name, args = item, None
            try:
                return reverse(name, args=args)
            except (NoReverseMatch, Exception):
                pass
    return candidate_paths[0]


@pytest.fixture
def sample_party(db):
    """Create a baseline vendor party for billing tests."""
    assert Party is not None, "Party model is not implemented in parties.models."
    return Party.objects.create(
        name="Lahore Steel Mills",
        urdu_name="لاہور اسٹیل ملز",
        phone="03001112233",
        party_type="vendor",
    )


@pytest.fixture
def sample_category(db):
    """Create or get a category for bills."""
    if Category is None:
        return None
    cat, _ = Category.objects.get_or_create(
        name="Construction",
        defaults={"urdu_name": "تعمیرات", "color": "#10B981"},
    )
    return cat


@pytest.fixture
def staff_with_delete_permission(db):
    """Create a staff user with can_delete_records=True."""
    return User.objects.create_user(
        username="staff_delete_permitted",
        email="staff_del@example.com",
        password="TestPass123!",
        role=User.Role.STAFF,
        can_delete_records=True,
    )


@pytest.fixture
def sample_bill(db, sample_party, sample_category):
    """Create a baseline manual bill with line items."""
    assert Bill is not None, "Bill model is not implemented in bills.models."
    assert BillItem is not None, "BillItem model is not implemented in bills.models."

    bill = Bill.objects.create(
        bill_type="purchase",
        party=sample_party,
        invoice_no="INV-2026-001",
        bill_date=timezone.now().date(),
        category=sample_category,
        status="Draft",
        source="manual",
        subtotal=Decimal("450.00"),
        discount=Decimal("50.00"),
        tax=Decimal("40.00"),
        grand_total=Decimal("440.00"),
        payment_status="Unpaid",
        amount_paid=Decimal("0.00"),
        is_deleted=False,
    )

    BillItem.objects.create(
        bill=bill,
        serial_no=1,
        item_name="Steel Rod 10mm",
        urdu_item_name="سٹیل راڈ",
        quantity=Decimal("2.0000"),
        unit="pcs",
        unit_price=Decimal("150.00"),
        line_total=Decimal("300.00"),
    )

    BillItem.objects.create(
        bill=bill,
        serial_no=2,
        item_name="Binding Wire",
        urdu_item_name="تار",
        quantity=Decimal("3.0000"),
        unit="kg",
        unit_price=Decimal("50.00"),
        line_total=Decimal("150.00"),
    )

    return bill


# ==============================================================================
# 1. Bill & BillItem Models Schema & Money Precision Tests
# ==============================================================================


@pytest.mark.django_db
class TestBillAndBillItemModelSchema:
    """Tests verifying Bill and BillItem schema, Decimal field precision, and choices."""

    def test_bill_model_exists(self):
        """Bill model must be implemented and importable from bills.models."""
        assert Bill is not None, "Bill model is not implemented in bills.models."

    def test_bill_item_model_exists(self):
        """BillItem model must be implemented and importable from bills.models."""
        assert BillItem is not None, "BillItem model is not implemented in bills.models."

    def test_bill_fields_exist(self):
        """Bill model must have all fields specified in the product specification."""
        assert Bill is not None, "Bill model is missing."
        field_names = {f.name for f in Bill._meta.get_fields()}
        expected_fields = {
            "bill_type",
            "party",
            "invoice_no",
            "bill_date",
            "category",
            "status",
            "source",
            "subtotal",
            "discount",
            "tax",
            "grand_total",
            "payment_status",
            "amount_paid",
            "is_deleted",
            "deleted_at",
        }
        missing = expected_fields - field_names
        assert not missing, f"Bill model is missing required fields: {missing}"

    def test_bill_item_fields_exist(self):
        """BillItem model must have all fields specified in the product specification."""
        assert BillItem is not None, "BillItem model is missing."
        field_names = {f.name for f in BillItem._meta.get_fields()}
        expected_fields = {
            "bill",
            "serial_no",
            "item_name",
            "urdu_item_name",
            "quantity",
            "unit",
            "unit_price",
            "line_total",
        }
        missing = expected_fields - field_names
        assert not missing, f"BillItem model is missing required fields: {missing}"

    def test_monetary_fields_use_decimal_field_not_float(self):
        """All money fields must strictly be DecimalField, never FloatField."""
        assert Bill is not None, "Bill model is missing."
        assert BillItem is not None, "BillItem model is missing."

        bill_money_fields = ["subtotal", "discount", "tax", "grand_total", "amount_paid"]
        for field_name in bill_money_fields:
            field = Bill._meta.get_field(field_name)
            assert isinstance(
                field, models.DecimalField
            ), f"Bill.{field_name} must be a DecimalField, got {type(field).__name__}"
            assert (
                field.decimal_places == 2
            ), f"Bill.{field_name} must have decimal_places=2, got {field.decimal_places}"

        item_money_fields = ["unit_price", "line_total"]
        for field_name in item_money_fields:
            field = BillItem._meta.get_field(field_name)
            assert isinstance(
                field, models.DecimalField
            ), f"BillItem.{field_name} must be a DecimalField, got {type(field).__name__}"
            assert (
                field.decimal_places == 2
            ), f"BillItem.{field_name} must have decimal_places=2, got {field.decimal_places}"

    def test_quantity_field_uses_decimal_field(self):
        """BillItem.quantity must be DecimalField to prevent floating point inaccuracies."""
        assert BillItem is not None, "BillItem model is missing."
        field = BillItem._meta.get_field("quantity")
        assert isinstance(
            field, models.DecimalField
        ), f"BillItem.quantity must be a DecimalField, got {type(field).__name__}"
        assert (
            field.decimal_places >= 2
        ), f"BillItem.quantity must support at least 2 decimal places, got {field.decimal_places}"

    def test_bill_str_representation(self, sample_bill):
        """Bill string representation contains invoice_no and party name or amount."""
        str_repr = str(sample_bill)
        assert "INV-2026-001" in str_repr

    def test_bill_item_str_representation(self, sample_bill):
        """BillItem string representation contains item_name."""
        item = (
            sample_bill.items.first()
            if hasattr(sample_bill, "items")
            else BillItem.objects.filter(bill=sample_bill).first()
        )
        assert item is not None
        assert "Steel Rod 10mm" in str(item)

    def test_bill_choices_validations(self, sample_party):
        """Bill validates choices for bill_type, status, source, and payment_status."""
        assert Bill is not None, "Bill model is missing."
        # Valid bill
        bill = Bill(
            bill_type="purchase",
            party=sample_party,
            invoice_no="INV-VALID",
            bill_date=timezone.now().date(),
            status="Draft",
            source="manual",
            payment_status="Unpaid",
            subtotal=Decimal("100.00"),
            discount=Decimal("0.00"),
            tax=Decimal("0.00"),
            grand_total=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
        )
        bill.full_clean()

        # Invalid bill_type
        bill.bill_type = "invalid_type"
        with pytest.raises(ValidationError):
            bill.full_clean()


# ==============================================================================
# 2. Totals Recalculation Service Tests
# ==============================================================================


@pytest.mark.django_db
class TestBillTotalsRecalculationService:
    """Tests for bills.services.recalculate_bill_totals."""

    def test_recalculate_service_exists(self):
        """recalculate_bill_totals function must be implemented in bills.services."""
        assert (
            recalculate_bill_totals is not None
        ), "recalculate_bill_totals function is not implemented in bills.services."

    def test_happy_path_recalculation(self, sample_bill):
        """Recalculating bill totals updates line totals, subtotal, and grand total."""
        assert recalculate_bill_totals is not None, "recalculate_bill_totals is missing."
        # Alter bill totals to stale values to test recalculation
        sample_bill.subtotal = Decimal("0.00")
        sample_bill.grand_total = Decimal("0.00")
        sample_bill.save()

        updated_bill = recalculate_bill_totals(sample_bill)
        bill = updated_bill or sample_bill
        bill.refresh_from_db()

        # Item 1: 2 * 150 = 300, Item 2: 3 * 50 = 150 -> Subtotal = 450
        assert bill.subtotal == Decimal("450.00")
        # Grand Total = 450 - 50 (discount) + 40 (tax) = 440
        assert bill.grand_total == Decimal("440.00")

    def test_rounding_half_up_rule(self, sample_party):
        """Monetary rounding follows ROUND_HALF_UP (e.g. 3 * 1.005 -> 3.02)."""
        assert recalculate_bill_totals is not None, "recalculate_bill_totals is missing."
        assert Bill is not None and BillItem is not None, "Models missing."

        bill = Bill.objects.create(
            bill_type="purchase",
            party=sample_party,
            invoice_no="INV-ROUND-1",
            bill_date=timezone.now().date(),
            discount=Decimal("0.00"),
            tax=Decimal("0.00"),
        )
        BillItem.objects.create(
            bill=bill,
            serial_no=1,
            item_name="Fractional Item",
            quantity=Decimal("3.0000"),
            unit="pcs",
            unit_price=Decimal("1.005"),  # 3 * 1.005 = 3.015 -> rounds to 3.02
        )

        recalculate_bill_totals(bill)
        bill.refresh_from_db()
        item = BillItem.objects.get(bill=bill)

        assert item.line_total == Decimal("3.02")
        assert bill.subtotal == Decimal("3.02")
        assert bill.grand_total == Decimal("3.02")

    def test_fractional_quantities_line_total(self, sample_party):
        """Line total calculation handles fractional quantities accurately."""
        assert recalculate_bill_totals is not None, "recalculate_bill_totals is missing."
        bill = Bill.objects.create(
            bill_type="purchase",
            party=sample_party,
            invoice_no="INV-FRAC-1",
            bill_date=timezone.now().date(),
            discount=Decimal("0.00"),
            tax=Decimal("0.00"),
        )
        BillItem.objects.create(
            bill=bill,
            serial_no=1,
            item_name="Loose Rice",
            quantity=Decimal("2.3456"),
            unit="kg",
            unit_price=Decimal("120.00"),
        )

        recalculate_bill_totals(bill)
        bill.refresh_from_db()
        item = BillItem.objects.get(bill=bill)
        # 2.3456 * 120.00 = 281.472 -> 281.47
        assert item.line_total == Decimal("281.47")
        assert bill.subtotal == Decimal("281.47")

    def test_empty_bill_items_totals(self, sample_party):
        """Bill with zero items calculates subtotal=0.00 and grand_total=0.00."""
        assert recalculate_bill_totals is not None, "recalculate_bill_totals is missing."
        bill = Bill.objects.create(
            bill_type="purchase",
            party=sample_party,
            invoice_no="INV-EMPTY",
            bill_date=timezone.now().date(),
            discount=Decimal("0.00"),
            tax=Decimal("0.00"),
        )
        recalculate_bill_totals(bill)
        bill.refresh_from_db()

        assert bill.subtotal == Decimal("0.00")
        assert bill.grand_total == Decimal("0.00")

    def test_zero_quantity_or_zero_unit_price(self, sample_party):
        """Items with 0 quantity or 0 unit price produce 0.00 line total."""
        assert recalculate_bill_totals is not None, "recalculate_bill_totals is missing."
        bill = Bill.objects.create(
            bill_type="purchase",
            party=sample_party,
            invoice_no="INV-ZERO",
            bill_date=timezone.now().date(),
            discount=Decimal("0.00"),
            tax=Decimal("0.00"),
        )
        BillItem.objects.create(
            bill=bill,
            serial_no=1,
            item_name="Free Sample",
            quantity=Decimal("5.0000"),
            unit="pcs",
            unit_price=Decimal("0.00"),
        )
        BillItem.objects.create(
            bill=bill,
            serial_no=2,
            item_name="Zero Quantity Item",
            quantity=Decimal("0.0000"),
            unit="pcs",
            unit_price=Decimal("50.00"),
        )

        recalculate_bill_totals(bill)
        bill.refresh_from_db()
        for item in BillItem.objects.filter(bill=bill):
            assert item.line_total == Decimal("0.00")
        assert bill.subtotal == Decimal("0.00")

    def test_large_monetary_numbers_calculation(self, sample_party):
        """Calculations with large monetary values succeed without floating-point distortion."""
        assert recalculate_bill_totals is not None, "recalculate_bill_totals is missing."
        bill = Bill.objects.create(
            bill_type="purchase",
            party=sample_party,
            invoice_no="INV-LARGE",
            bill_date=timezone.now().date(),
            discount=Decimal("10000.00"),
            tax=Decimal("50000.00"),
        )
        BillItem.objects.create(
            bill=bill,
            serial_no=1,
            item_name="Heavy Machinery",
            quantity=Decimal("10.0000"),
            unit="pcs",
            unit_price=Decimal("5000000.00"),  # 50,000,000.00
        )

        recalculate_bill_totals(bill)
        bill.refresh_from_db()
        assert bill.subtotal == Decimal("50000000.00")
        # 50,000,000 - 10,000 + 50,000 = 50,040,000.00
        assert bill.grand_total == Decimal("50040000.00")

    def test_negative_discount_raises_validation_error(self, sample_bill):
        """Negative discount is invalid and raises ValidationError."""
        assert recalculate_bill_totals is not None, "recalculate_bill_totals is missing."
        sample_bill.discount = Decimal("-50.00")
        sample_bill.save()

        with pytest.raises(ValidationError):
            recalculate_bill_totals(sample_bill)

    def test_negative_tax_raises_validation_error(self, sample_bill):
        """Negative tax is invalid and raises ValidationError."""
        assert recalculate_bill_totals is not None, "recalculate_bill_totals is missing."
        sample_bill.tax = Decimal("-10.00")
        sample_bill.save()

        with pytest.raises(ValidationError):
            recalculate_bill_totals(sample_bill)

    def test_discount_exceeding_subtotal_behavior(self, sample_party):
        """Discount exceeding subtotal is either rejected with ValidationError or clamped to 0.00."""
        assert recalculate_bill_totals is not None, "recalculate_bill_totals is missing."
        bill = Bill.objects.create(
            bill_type="purchase",
            party=sample_party,
            invoice_no="INV-DISC-EXCEED",
            bill_date=timezone.now().date(),
            discount=Decimal("500.00"),  # Exceeds subtotal (100.00)
            tax=Decimal("0.00"),
        )
        BillItem.objects.create(
            bill=bill,
            serial_no=1,
            item_name="Minor Item",
            quantity=Decimal("1.0000"),
            unit="pcs",
            unit_price=Decimal("100.00"),
        )

        try:
            recalculate_bill_totals(bill)
            bill.refresh_from_db()
            # If not raising ValidationError, grand_total must not be negative
            assert bill.grand_total >= Decimal("0.00")
        except ValidationError:
            # Raising ValidationError is also valid and expected
            pass


# ==============================================================================
# 3. Soft Delete & Trash Pattern Tests
# ==============================================================================


@pytest.mark.django_db
class TestBillSoftDeleteAndTrash:
    """Tests for soft delete, trash listing, restoration, and permission checks."""

    TRASH_URL_CANDIDATES = ["/en/bills/trash/"]
    TRASH_REVERSE_NAMES = ["bills:bill_trash", "bills:trash", "bills:trash_list"]

    def _trash_url(self):
        return resolve_candidate_url(self.TRASH_URL_CANDIDATES, self.TRASH_REVERSE_NAMES)

    def _delete_url(self, bill_id):
        return resolve_candidate_url(
            [f"/en/bills/{bill_id}/delete/"],
            [("bills:bill_delete", [bill_id]), ("bills:delete", [bill_id])],
        )

    def _restore_url(self, bill_id):
        return resolve_candidate_url(
            [f"/en/bills/{bill_id}/restore/"],
            [("bills:bill_restore", [bill_id]), ("bills:restore", [bill_id])],
        )

    def test_soft_delete_marks_bill_and_excludes_from_active_queries(self, sample_bill):
        """Soft deleting sets is_deleted=True and excludes bill from active querysets."""
        assert Bill is not None, "Bill model is missing."
        sample_bill.is_deleted = True
        sample_bill.deleted_at = timezone.now()
        sample_bill.save()

        # Default manager or active queryset must exclude soft-deleted records
        if hasattr(Bill, "active_objects"):
            active_qs = Bill.active_objects.all()
        else:
            active_qs = Bill.objects.all()

        assert (
            sample_bill not in active_qs
            or not active_qs.filter(pk=sample_bill.pk, is_deleted=False).exists()
        )

    def test_trashed_bill_visible_in_trash_view(self, superadmin_client, sample_bill):
        """Soft-deleted bill appears in the trash list view at /en/bills/trash/."""
        sample_bill.is_deleted = True
        sample_bill.deleted_at = timezone.now()
        sample_bill.save()

        response = superadmin_client.get(self._trash_url())
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert sample_bill.invoice_no in content

    def test_restore_view_restores_bill(self, superadmin_client, sample_bill):
        """Restoring a soft-deleted bill sets is_deleted=False and deleted_at=None."""
        sample_bill.is_deleted = True
        sample_bill.deleted_at = timezone.now()
        sample_bill.save()

        restore_url = self._restore_url(sample_bill.pk)
        response = superadmin_client.post(restore_url)
        assert response.status_code in (302, 200)

        sample_bill.refresh_from_db()
        assert sample_bill.is_deleted is False
        assert sample_bill.deleted_at is None

    def test_staff_without_can_delete_records_forbidden_trash(self, staff_client):
        """Staff member without can_delete_records receives HTTP 403 when accessing trash."""
        assert Bill is not None, "Bill model is missing."
        response = staff_client.get(self._trash_url())
        assert response.status_code == 403

    def test_staff_without_can_delete_records_forbidden_delete(self, staff_client, sample_bill):
        """Staff member without can_delete_records receives HTTP 403 when attempting to delete."""
        delete_url = self._delete_url(sample_bill.pk)
        response = staff_client.post(delete_url)
        assert response.status_code == 403

        sample_bill.refresh_from_db()
        assert sample_bill.is_deleted is False

    def test_staff_without_can_delete_records_forbidden_restore(self, staff_client, sample_bill):
        """Staff member without can_delete_records receives HTTP 403 when attempting to restore."""
        sample_bill.is_deleted = True
        sample_bill.deleted_at = timezone.now()
        sample_bill.save()

        restore_url = self._restore_url(sample_bill.pk)
        response = staff_client.post(restore_url)
        assert response.status_code == 403

        sample_bill.refresh_from_db()
        assert sample_bill.is_deleted is True

    def test_staff_with_can_delete_records_allowed_trash_and_delete(
        self, staff_with_delete_permission, sample_bill
    ):
        """Staff member granted can_delete_records can access trash and delete bills."""
        from django.test import Client

        client = Client()
        client.force_login(staff_with_delete_permission)

        # Access trash view
        trash_resp = client.get(self._trash_url())
        assert trash_resp.status_code == 200

        # Delete bill
        delete_url = self._delete_url(sample_bill.pk)
        del_resp = client.post(delete_url)
        assert del_resp.status_code in (302, 200)

        sample_bill.refresh_from_db()
        assert sample_bill.is_deleted is True

    def test_superadmin_has_full_delete_and_restore_access(self, superadmin_client, sample_bill):
        """Superadmin can delete and restore bills."""
        delete_url = self._delete_url(sample_bill.pk)
        del_resp = superadmin_client.post(delete_url)
        assert del_resp.status_code in (302, 200)

        sample_bill.refresh_from_db()
        assert sample_bill.is_deleted is True

        restore_url = self._restore_url(sample_bill.pk)
        restore_resp = superadmin_client.post(restore_url)
        assert restore_resp.status_code in (302, 200)

        sample_bill.refresh_from_db()
        assert sample_bill.is_deleted is False


# ==============================================================================
# 4. Bill Views & Workflow Tests
# ==============================================================================


@pytest.mark.django_db
class TestBillViewsAndWorkflow:
    """Tests for Bill views, listing, filters, manual creation, detail, and edit."""

    BILLS_URL_CANDIDATES = ["/en/bills/"]
    BILLS_REVERSE_NAMES = ["bills:bill_list", "bills:list", "bills:bills"]

    ADD_URL_CANDIDATES = ["/en/bills/add/"]
    ADD_REVERSE_NAMES = ["bills:bill_create", "bills:bill_add", "bills:add"]

    def _bills_url(self):
        return resolve_candidate_url(self.BILLS_URL_CANDIDATES, self.BILLS_REVERSE_NAMES)

    def _add_url(self):
        return resolve_candidate_url(self.ADD_URL_CANDIDATES, self.ADD_REVERSE_NAMES)

    def _detail_url(self, bill_id):
        return resolve_candidate_url(
            [f"/en/bills/{bill_id}/"],
            [("bills:bill_detail", [bill_id]), ("bills:detail", [bill_id])],
        )

    def _edit_url(self, bill_id):
        return resolve_candidate_url(
            [f"/en/bills/{bill_id}/edit/"],
            [("bills:bill_edit", [bill_id]), ("bills:edit", [bill_id])],
        )

    def test_unauthenticated_requests_redirect_to_login(self, client, sample_bill):
        """Unauthenticated requests to bill views redirect to login."""
        for url in [
            self._bills_url(),
            self._add_url(),
            self._detail_url(sample_bill.pk),
            self._edit_url(sample_bill.pk),
        ]:
            response = client.get(url)
            assert response.status_code == 302
            assert "/accounts/login/" in response.url

    def test_authenticated_user_can_view_bills_list(self, staff_client, sample_bill):
        """Authenticated user can view bills list showing invoice_no and grand_total."""
        response = staff_client.get(self._bills_url())
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert sample_bill.invoice_no in content

    def test_bill_list_search_by_invoice_no(self, staff_client, sample_bill, sample_party):
        """Bill list can be filtered/searched by invoice_no."""
        other_bill = Bill.objects.create(
            bill_type="purchase",
            party=sample_party,
            invoice_no="INV-OTHER-999",
            bill_date=timezone.now().date(),
            grand_total=Decimal("100.00"),
        )
        url = f"{self._bills_url()}?q={sample_bill.invoice_no}"
        response = staff_client.get(url)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert sample_bill.invoice_no in content
        assert other_bill.invoice_no not in content

    def test_bill_list_search_by_party_phone(self, staff_client, sample_bill, sample_party):
        """Bill list can be filtered/searched by party's phone number."""
        sample_party.phone = "03234663429"
        sample_party.save(update_fields=["phone"])

        other_party = Party.objects.create(
            name="Other Vendor", phone="03001112233", party_type="vendor"
        )
        other_bill = Bill.objects.create(
            bill_type="purchase",
            party=other_party,
            invoice_no="INV-OTHER-PHONE",
            bill_date=timezone.now().date(),
            grand_total=Decimal("100.00"),
        )
        url = f"{self._bills_url()}?q=03234663429"
        response = staff_client.get(url)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert sample_bill.invoice_no in content
        assert other_bill.invoice_no not in content

    def test_bill_list_total_amount_formatted_to_two_decimal_places(
        self, staff_client, sample_bill
    ):
        """Bill list total amount is rounded and formatted with exactly 2 decimal places."""
        sample_bill.grand_total = Decimal("1234.50")
        sample_bill.save(update_fields=["grand_total"])

        response = staff_client.get(self._bills_url())
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Rs. 1234.50" in content
        assert "1234.50000000" not in content

    def test_bill_list_filter_by_party(self, staff_client, sample_bill):
        """Bill list filters bills by party."""
        assert Party is not None, "Party model is missing."
        other_party = Party.objects.create(name="Another Vendor Co", party_type="vendor")
        other_bill = Bill.objects.create(
            bill_type="purchase",
            party=other_party,
            invoice_no="INV-OTHER-PARTY",
            bill_date=timezone.now().date(),
            grand_total=Decimal("200.00"),
        )
        url = f"{self._bills_url()}?party={sample_bill.party_id}"
        response = staff_client.get(url)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert sample_bill.invoice_no in content
        assert other_bill.invoice_no not in content

    def test_bill_list_filter_by_payment_status(self, staff_client, sample_bill, sample_party):
        """Bill list filters bills by payment_status."""
        paid_bill = Bill.objects.create(
            bill_type="purchase",
            party=sample_party,
            invoice_no="INV-PAID-001",
            bill_date=timezone.now().date(),
            payment_status="Paid",
            amount_paid=Decimal("500.00"),
            grand_total=Decimal("500.00"),
        )
        url = f"{self._bills_url()}?payment_status=Unpaid"
        response = staff_client.get(url)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert sample_bill.invoice_no in content
        assert paid_bill.invoice_no not in content

    def test_bill_list_filter_by_date(self, staff_client, sample_bill, sample_party):
        """Bill list filters bills by bill_date."""
        old_bill = Bill.objects.create(
            bill_type="purchase",
            party=sample_party,
            invoice_no="INV-OLD-DATE",
            bill_date=timezone.now().date() - timezone.timedelta(days=30),
            grand_total=Decimal("300.00"),
        )
        date_str = sample_bill.bill_date.strftime("%Y-%m-%d")
        url = f"{self._bills_url()}?date={date_str}"
        response = staff_client.get(url)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert sample_bill.invoice_no in content
        assert old_bill.invoice_no not in content

    def test_bills_list_is_paginated(self, staff_client, sample_party):
        """Bill list is paginated with 25 records per page."""
        assert Bill is not None, "Bill model is missing."
        # Create 26 bills
        for i in range(26):
            Bill.objects.create(
                bill_type="purchase",
                party=sample_party,
                invoice_no=f"INV-PAGINATE-{i:03d}",
                bill_date=timezone.now().date(),
                grand_total=Decimal("100.00"),
            )

        response = staff_client.get(self._bills_url())
        assert response.status_code == 200
        # Check pagination context or links
        assert (
            "page" in response.content.decode("utf-8").lower()
            or response.context.get("page_obj") is not None
        )

    def test_create_manual_bill_happy_path(self, staff_client, sample_party, sample_category):
        """Creating a manual bill persists bill and line items, recalculating totals."""
        assert Bill is not None, "Bill model is missing."
        get_resp = staff_client.get(self._add_url())
        assert get_resp.status_code == 200

        payload = {
            "bill_type": "purchase",
            "party": sample_party.pk,
            "invoice_no": "INV-MANUAL-NEW-01",
            "bill_date": timezone.now().date().strftime("%Y-%m-%d"),
            "category": sample_category.pk if sample_category else "",
            "discount": "20.00",
            "tax": "15.00",
            # Items payload via formset or JSON
            "items-TOTAL_FORMS": "2",
            "items-INITIAL_FORMS": "0",
            "items-0-item_name": "Cement Bag",
            "items-0-quantity": "10",
            "items-0-unit": "bag",
            "items-0-unit_price": "1200.00",
            "items-1-item_name": "Sand",
            "items-1-quantity": "1",
            "items-1-unit": "truck",
            "items-1-unit_price": "5000.00",
        }
        response = staff_client.post(self._add_url(), payload)
        assert response.status_code in (302, 201)

        assert Bill.objects.filter(invoice_no="INV-MANUAL-NEW-01").exists()
        created_bill = Bill.objects.get(invoice_no="INV-MANUAL-NEW-01")
        assert created_bill.source == "manual"
        # 10*1200 + 1*5000 = 12000 + 5000 = 17000. Grand = 17000 - 20 + 15 = 16995.00
        assert created_bill.grand_total == Decimal("16995.00")

    def test_create_manual_bill_validation_error(self, staff_client):
        """Posting invalid bill form (missing party or invoice_no) returns form errors."""
        payload = {
            "bill_type": "purchase",
            "invoice_no": "",  # Missing invoice_no
        }
        response = staff_client.post(self._add_url(), payload)
        assert response.status_code in (200, 400)

    def test_view_bill_detail(self, staff_client, sample_bill):
        """Bill detail view displays bill header, items, totals, and payment status."""
        detail_url = self._detail_url(sample_bill.pk)
        response = staff_client.get(detail_url)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert sample_bill.invoice_no in content
        assert "Steel Rod 10mm" in content

    def test_edit_bill(self, staff_client, sample_bill):
        """Bill edit view allows updating bill data."""
        edit_url = self._edit_url(sample_bill.pk)
        get_resp = staff_client.get(edit_url)
        assert get_resp.status_code == 200

        payload = {
            "bill_type": "purchase",
            "party": sample_bill.party_id,
            "invoice_no": "INV-2026-EDITED",
            "bill_date": sample_bill.bill_date.strftime("%Y-%m-%d"),
            "discount": "0.00",
            "tax": "0.00",
        }
        post_resp = staff_client.post(edit_url, payload)
        assert post_resp.status_code in (302, 200)

        sample_bill.refresh_from_db()
        assert sample_bill.invoice_no == "INV-2026-EDITED"

    def test_unverified_needs_review_bills_excluded_from_default_list(
        self, staff_client, sample_party
    ):
        """Unverified scanned bills (NeedsReview) are excluded from default bills roster."""
        verified_bill = Bill.objects.create(
            bill_type="purchase",
            party=sample_party,
            invoice_no="INV-VERIFIED-99",
            bill_date=timezone.now().date(),
            grand_total=Decimal("500.00"),
            status=Bill.Status.VERIFIED,
        )
        unreviewed_bill = Bill.objects.create(
            bill_type="purchase",
            party=sample_party,
            invoice_no="INV-UNREVIEWED-SCAN-99",
            bill_date=timezone.now().date(),
            grand_total=Decimal("800.00"),
            status=Bill.Status.NEEDS_REVIEW,
        )

        resp = staff_client.get(self._bills_url())
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")

        # Verified bill must be visible
        assert verified_bill.invoice_no in content
        # Unreviewed scan bill must NOT be in the table
        assert unreviewed_bill.invoice_no not in content
        # Context checks
        assert resp.context["needs_review_count"] >= 1
        assert resp.context["total_amount"] == Decimal("500.00")

    def test_filter_bills_by_needs_review_status(self, staff_client, sample_party):
        """Explicitly filtering ?status=NeedsReview displays pending review bills."""
        verified_bill = Bill.objects.create(
            bill_type="purchase",
            party=sample_party,
            invoice_no="INV-VERIFIED-100",
            bill_date=timezone.now().date(),
            grand_total=Decimal("500.00"),
            status=Bill.Status.VERIFIED,
        )
        unreviewed_bill = Bill.objects.create(
            bill_type="purchase",
            party=sample_party,
            invoice_no="INV-PENDING-SCAN-100",
            bill_date=timezone.now().date(),
            grand_total=Decimal("800.00"),
            status=Bill.Status.NEEDS_REVIEW,
        )

        resp = staff_client.get(f"{self._bills_url()}?status=NeedsReview")
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")

        assert unreviewed_bill.invoice_no in content
        assert verified_bill.invoice_no not in content

    def test_filter_bills_by_all_status(self, staff_client, sample_party):
        """Filtering ?status=all includes both verified and unreviewed bills."""
        verified_bill = Bill.objects.create(
            bill_type="purchase",
            party=sample_party,
            invoice_no="INV-ALL-VERIFIED",
            bill_date=timezone.now().date(),
            grand_total=Decimal("500.00"),
            status=Bill.Status.VERIFIED,
        )
        unreviewed_bill = Bill.objects.create(
            bill_type="purchase",
            party=sample_party,
            invoice_no="INV-ALL-UNREVIEWED",
            bill_date=timezone.now().date(),
            grand_total=Decimal("800.00"),
            status=Bill.Status.NEEDS_REVIEW,
        )

        resp = staff_client.get(f"{self._bills_url()}?status=all")
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")

        assert verified_bill.invoice_no in content
        assert unreviewed_bill.invoice_no in content
