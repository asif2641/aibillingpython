"""tests/test_payments.py
========================
Test-first test suite for Phase 3: Payment Model, Payment Recording Service,
and Payment Views.

Coverage:
- Payment Model Schema & Constraints:
  - Fields: party, bill, amount, payment_date, payment_method, reference, notes,
    created_by, is_deleted, deleted_at.
  - Amount field uses DecimalField(max_digits=14, decimal_places=2), never float.
  - Choices: cash, bank_transfer, cheque, online.
  - Nullable bill allows unallocated on-account payments.
  - Soft delete support.
- Payment Recording & Status Transition Service (ledger.services.record_payment):
  - Validates amount > 0; raises ValidationError for zero or negative amount.
  - If bill provided:
    - Verifies bill party matches payment party (raises ValidationError if mismatched).
    - Updates bill.amount_paid += amount.
    - Transitions bill.payment_status:
      - amount_paid == 0 -> 'Unpaid'
      - 0 < amount_paid < grand_total -> 'Partially Paid'
      - amount_paid >= grand_total -> 'Paid'
    - Multi-payment progression: partial -> partial -> paid.
    - Overpayment handling: amount_paid >= grand_total sets 'Paid'.
  - If bill is None: creates standalone on-account payment.
  - Monetary precision: rounds/validates via money_round.
- Views & Endpoints:
  - Unauthenticated access redirects to login.
  - Record payment view / form (/en/ledger/payments/add/ or /en/bills/<id>/payment/).
  - Form validation: rejects negative or zero amounts.
  - Authenticated staff and superadmin can record payments.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

try:
    from ledger.models import Payment
except (ImportError, AttributeError):
    Payment = None

try:
    from ledger.services import record_payment
except (ImportError, AttributeError):
    record_payment = None

try:
    from parties.models import Party
except (ImportError, AttributeError):
    Party = None

try:
    from bills.models import Bill
except (ImportError, AttributeError):
    Bill = None

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
def sample_vendor(db):
    """Create a baseline vendor party."""
    assert Party is not None, "Party model is not implemented in parties.models."
    return Party.objects.create(
        name="Habib Oil Mills",
        urdu_name="حبیب آئل ملز",
        phone="03007654321",
        party_type="vendor",
    )


@pytest.fixture
def sample_customer(db):
    """Create a baseline customer party."""
    assert Party is not None, "Party model is not implemented in parties.models."
    return Party.objects.create(
        name="Tariq Mahmood",
        urdu_name="طارق محمود",
        phone="03215554433",
        party_type="customer",
    )


@pytest.fixture
def sample_bill(db, sample_vendor):
    """Create a baseline unpaid bill with grand_total=1000.00."""
    assert Bill is not None, "Bill model is not implemented in bills.models."
    return Bill.objects.create(
        bill_type="purchase",
        party=sample_vendor,
        invoice_no="INV-PAY-001",
        bill_date=timezone.now().date(),
        subtotal=Decimal("1000.00"),
        discount=Decimal("0.00"),
        tax=Decimal("0.00"),
        grand_total=Decimal("1000.00"),
        amount_paid=Decimal("0.00"),
        payment_status="Unpaid",
    )


# ==============================================================================
# 1. Payment Model Schema & Constraints Tests
# ==============================================================================


@pytest.mark.django_db
class TestPaymentModelSchema:
    """Tests verifying Payment model schema, fields, precision, and constraints."""

    def test_payment_model_exists(self):
        """Payment model must be implemented and importable from ledger.models."""
        assert Payment is not None, "Payment model is not implemented in ledger.models."

    def test_payment_fields_exist(self):
        """Payment model must define all fields required by the spec."""
        assert Payment is not None, "Payment model is missing."
        field_names = {f.name for f in Payment._meta.get_fields()}
        expected_fields = {
            "party",
            "bill",
            "amount",
            "payment_date",
            "payment_method",
            "reference",
            "notes",
            "created_by",
            "is_deleted",
            "deleted_at",
        }
        missing = expected_fields - field_names
        assert not missing, f"Payment model is missing required fields: {missing}"

    def test_payment_amount_field_is_decimal_field(self):
        """Payment.amount must strictly be a DecimalField, never FloatField."""
        assert Payment is not None, "Payment model is missing."
        field = Payment._meta.get_field("amount")
        assert isinstance(
            field, models.DecimalField
        ), f"Payment.amount must be DecimalField, got {type(field).__name__}"
        assert (
            field.decimal_places == 2
        ), f"Payment.amount must have decimal_places=2, got {field.decimal_places}"

    def test_create_payment_happy_path(self, sample_vendor, sample_bill, staff_user):
        """Payment record can be created, persisted, and retrieved with full details."""
        assert Payment is not None, "Payment model is missing."
        payment = Payment.objects.create(
            party=sample_vendor,
            bill=sample_bill,
            amount=Decimal("500.00"),
            payment_date=timezone.now().date(),
            payment_method="cash",
            reference="RCPT-001",
            notes="Initial 50% deposit",
            created_by=staff_user,
        )
        assert payment.pk is not None
        refreshed = Payment.objects.get(pk=payment.pk)
        assert refreshed.party == sample_vendor
        assert refreshed.bill == sample_bill
        assert refreshed.amount == Decimal("500.00")
        assert refreshed.payment_method == "cash"
        assert refreshed.reference == "RCPT-001"
        assert refreshed.created_by == staff_user
        assert refreshed.is_deleted is False

    def test_payment_str_representation(self, sample_vendor):
        """Payment string representation contains party name and amount."""
        assert Payment is not None, "Payment model is missing."
        payment = Payment.objects.create(
            party=sample_vendor,
            amount=Decimal("750.00"),
            payment_date=timezone.now().date(),
            payment_method="cash",
        )
        str_repr = str(payment)
        assert "Habib Oil Mills" in str_repr or "750" in str_repr

    def test_payment_method_choices(self, sample_vendor):
        """Payment accepts all valid payment methods: cash, bank_transfer, cheque, online."""
        assert Payment is not None, "Payment model is missing."
        for method in ["cash", "bank_transfer", "cheque", "online"]:
            p = Payment.objects.create(
                party=sample_vendor,
                amount=Decimal("100.00"),
                payment_date=timezone.now().date(),
                payment_method=method,
            )
            assert p.payment_method == method
            p.full_clean()

    def test_payment_method_invalid_choice_rejected(self, sample_vendor):
        """Invalid payment method raises ValidationError on full_clean()."""
        assert Payment is not None, "Payment model is missing."
        p = Payment(
            party=sample_vendor,
            amount=Decimal("100.00"),
            payment_date=timezone.now().date(),
            payment_method="crypto_coins",
        )
        with pytest.raises(ValidationError):
            p.full_clean()

    def test_payment_nullable_bill_for_on_account_payments(self, sample_vendor):
        """Payment can be created without a bill (unallocated on-account payment)."""
        assert Payment is not None, "Payment model is missing."
        payment = Payment.objects.create(
            party=sample_vendor,
            bill=None,
            amount=Decimal("300.00"),
            payment_date=timezone.now().date(),
            payment_method="bank_transfer",
            reference="IBFT-998877",
        )
        assert payment.pk is not None
        assert payment.bill is None

    def test_payment_soft_delete(self, sample_vendor):
        """Payment supports soft deletion with is_deleted=True and deleted_at timestamp."""
        assert Payment is not None, "Payment model is missing."
        payment = Payment.objects.create(
            party=sample_vendor,
            amount=Decimal("200.00"),
            payment_date=timezone.now().date(),
            payment_method="cash",
        )
        payment.is_deleted = True
        payment.deleted_at = timezone.now()
        payment.save()

        refreshed = Payment.objects.get(pk=payment.pk)
        assert refreshed.is_deleted is True
        assert refreshed.deleted_at is not None


# ==============================================================================
# 2. Payment Recording & Status Transition Service Tests
# ==============================================================================


@pytest.mark.django_db
class TestPaymentRecordingService:
    """Tests for ledger.services.record_payment business logic and bill status transitions."""

    def test_record_payment_service_exists(self):
        """record_payment function must be implemented in ledger.services."""
        assert (
            record_payment is not None
        ), "record_payment function is not implemented in ledger.services."

    def test_full_payment_transitions_bill_to_paid(self, sample_vendor, sample_bill):
        """Paying the exact grand_total sets bill.amount_paid and transitions status to 'Paid'."""
        assert record_payment is not None, "record_payment is missing."
        assert sample_bill.payment_status == "Unpaid"
        assert sample_bill.amount_paid == Decimal("0.00")

        payment = record_payment(
            party=sample_vendor,
            amount=Decimal("1000.00"),
            bill=sample_bill,
            payment_method="bank_transfer",
            reference="TXN-FULL-01",
        )
        assert payment.pk is not None
        assert payment.amount == Decimal("1000.00")

        sample_bill.refresh_from_db()
        assert sample_bill.amount_paid == Decimal("1000.00")
        assert sample_bill.payment_status == "Paid"

    def test_partial_payment_transitions_bill_to_partially_paid(self, sample_vendor, sample_bill):
        """Paying less than grand_total updates amount_paid and transitions status to 'Partially Paid'."""
        assert record_payment is not None, "record_payment is missing."
        payment = record_payment(
            party=sample_vendor,
            amount=Decimal("400.00"),
            bill=sample_bill,
            payment_method="cash",
        )
        assert payment.pk is not None

        sample_bill.refresh_from_db()
        assert sample_bill.amount_paid == Decimal("400.00")
        assert sample_bill.payment_status == "Partially Paid"

    def test_sequential_partial_payments_progress_to_paid(self, sample_vendor, sample_bill):
        """Multiple partial payments incrementally update amount_paid until bill is 'Paid'."""
        assert record_payment is not None, "record_payment is missing."

        # Payment 1: 400.00 -> Partially Paid
        record_payment(party=sample_vendor, amount=Decimal("400.00"), bill=sample_bill)
        sample_bill.refresh_from_db()
        assert sample_bill.amount_paid == Decimal("400.00")
        assert sample_bill.payment_status == "Partially Paid"

        # Payment 2: 350.00 -> 750.00 total -> Still Partially Paid
        record_payment(party=sample_vendor, amount=Decimal("350.00"), bill=sample_bill)
        sample_bill.refresh_from_db()
        assert sample_bill.amount_paid == Decimal("750.00")
        assert sample_bill.payment_status == "Partially Paid"

        # Payment 3: 250.00 -> 1000.00 total -> Now Paid
        record_payment(party=sample_vendor, amount=Decimal("250.00"), bill=sample_bill)
        sample_bill.refresh_from_db()
        assert sample_bill.amount_paid == Decimal("1000.00")
        assert sample_bill.payment_status == "Paid"

    def test_overpayment_sets_bill_to_paid(self, sample_vendor, sample_bill):
        """Paying more than grand_total records the amount paid and marks bill 'Paid'."""
        assert record_payment is not None, "record_payment is missing."
        record_payment(party=sample_vendor, amount=Decimal("1200.00"), bill=sample_bill)
        sample_bill.refresh_from_db()

        assert sample_bill.amount_paid == Decimal("1200.00")
        assert sample_bill.payment_status == "Paid"

    def test_payment_without_bill_records_on_account(self, sample_vendor):
        """Recording payment with bill=None creates an unallocated payment record."""
        assert record_payment is not None, "record_payment is missing."
        payment = record_payment(
            party=sample_vendor,
            amount=Decimal("500.00"),
            bill=None,
            payment_method="cheque",
            reference="CHQ-554433",
        )
        assert payment.pk is not None
        assert payment.party == sample_vendor
        assert payment.bill is None
        assert payment.amount == Decimal("500.00")

    def test_reject_negative_payment_amount(self, sample_vendor, sample_bill):
        """Negative payment amount is invalid and raises ValidationError."""
        assert record_payment is not None, "record_payment is missing."
        with pytest.raises(ValidationError):
            record_payment(party=sample_vendor, amount=Decimal("-100.00"), bill=sample_bill)

    def test_reject_zero_payment_amount(self, sample_vendor, sample_bill):
        """Zero payment amount is invalid and raises ValidationError."""
        assert record_payment is not None, "record_payment is missing."
        with pytest.raises(ValidationError):
            record_payment(party=sample_vendor, amount=Decimal("0.00"), bill=sample_bill)

    def test_reject_mismatched_bill_party(self, sample_vendor, sample_customer, sample_bill):
        """Attempting to pay a bill with a mismatched party raises ValidationError."""
        assert record_payment is not None, "record_payment is missing."
        # sample_bill belongs to sample_vendor, but we attempt payment for sample_customer
        with pytest.raises(ValidationError):
            record_payment(
                party=sample_customer,
                amount=Decimal("500.00"),
                bill=sample_bill,
            )

    def test_payment_amount_rounded_with_money_round(self, sample_vendor, sample_bill):
        """Payment amount with extra fractional decimals is rounded to 2 places using money_round."""
        assert record_payment is not None, "record_payment is missing."
        payment = record_payment(
            party=sample_vendor,
            amount=Decimal("250.555"),  # Rounds to 250.56
            bill=sample_bill,
        )
        assert payment.amount == Decimal("250.56")
        sample_bill.refresh_from_db()
        assert sample_bill.amount_paid == Decimal("250.56")

    def test_created_by_user_associated_with_payment(self, sample_vendor, staff_user):
        """Passing created_by user persists the user association."""
        assert record_payment is not None, "record_payment is missing."
        payment = record_payment(
            party=sample_vendor,
            amount=Decimal("300.00"),
            created_by=staff_user,
        )
        assert payment.created_by == staff_user


# ==============================================================================
# 3. Payment Views & Endpoints Tests
# ==============================================================================


@pytest.mark.django_db
class TestPaymentViewsAndEndpoints:
    """Tests for Payment recording views, URLs, forms, and permission checks."""

    ADD_PAYMENT_URL_CANDIDATES = ["/en/ledger/payments/add/"]
    ADD_PAYMENT_REVERSE_NAMES = [
        "ledger:payment_add",
        "ledger:payment_create",
        "ledger:record_payment",
        "ledger:add_payment",
    ]

    def _add_payment_url(self):
        return resolve_candidate_url(
            self.ADD_PAYMENT_URL_CANDIDATES, self.ADD_PAYMENT_REVERSE_NAMES
        )

    def _bill_payment_url(self, bill_id):
        return resolve_candidate_url(
            [f"/en/bills/{bill_id}/payment/"],
            [("bills:bill_payment", [bill_id]), ("bills:payment", [bill_id])],
        )

    def test_unauthenticated_requests_redirect_to_login(self, client, sample_bill):
        """Unauthenticated requests to payment views redirect to login."""
        for url in [self._add_payment_url(), self._bill_payment_url(sample_bill.pk)]:
            response = client.get(url)
            assert response.status_code == 302
            assert "/accounts/login/" in response.url

    def test_authenticated_user_can_view_add_payment_form(self, staff_client):
        """Authenticated user can GET the record payment form."""
        response = staff_client.get(self._add_payment_url())
        assert response.status_code == 200

    def test_authenticated_user_can_record_payment_for_party(self, staff_client, sample_vendor):
        """Authenticated user can POST to record a payment for a party."""
        assert Payment is not None, "Payment model is missing."
        payload = {
            "party": sample_vendor.pk,
            "amount": "650.00",
            "payment_date": timezone.now().date().strftime("%Y-%m-%d"),
            "payment_method": "cash",
            "reference": "RCPT-PARTY-01",
            "notes": "Direct on-account payment",
        }
        response = staff_client.post(self._add_payment_url(), payload)
        assert response.status_code in (302, 201)

        assert Payment.objects.filter(reference="RCPT-PARTY-01").exists()
        created = Payment.objects.get(reference="RCPT-PARTY-01")
        assert created.amount == Decimal("650.00")
        assert created.party == sample_vendor

    def test_authenticated_user_can_record_payment_for_bill(
        self, staff_client, sample_vendor, sample_bill
    ):
        """Posting payment for a specific bill updates bill payment status."""
        assert Payment is not None, "Payment model is missing."
        # Try bill payment URL first or general payment URL with bill field
        bill_pay_url = self._bill_payment_url(sample_bill.pk)
        payload = {
            "party": sample_vendor.pk,
            "bill": sample_bill.pk,
            "amount": "1000.00",
            "payment_date": timezone.now().date().strftime("%Y-%m-%d"),
            "payment_method": "bank_transfer",
            "reference": "BILL-PAY-TXN-01",
        }
        # Attempt POST to bill specific payment endpoint or add payment endpoint
        response = staff_client.post(bill_pay_url, payload)
        if response.status_code == 404:
            response = staff_client.post(self._add_payment_url(), payload)

        assert response.status_code in (302, 201)
        sample_bill.refresh_from_db()
        assert sample_bill.amount_paid == Decimal("1000.00")
        assert sample_bill.payment_status == "Paid"

    def test_record_payment_invalid_amount_returns_form_error(self, staff_client, sample_vendor):
        """Posting invalid amount (negative or 0) returns form error."""
        payload = {
            "party": sample_vendor.pk,
            "amount": "-50.00",
            "payment_date": timezone.now().date().strftime("%Y-%m-%d"),
            "payment_method": "cash",
        }
        response = staff_client.post(self._add_payment_url(), payload)
        assert response.status_code in (200, 400)

    def test_staff_and_superadmin_permissions_for_payments(
        self, staff_client, superadmin_client, sample_vendor
    ):
        """Both staff and superadmin have permissions to access payment creation."""
        staff_resp = staff_client.get(self._add_payment_url())
        assert staff_resp.status_code == 200

        admin_resp = superadmin_client.get(self._add_payment_url())
        assert admin_resp.status_code == 200

    def test_payment_form_rejects_bill_belonging_to_different_party(
        self, sample_vendor, sample_customer, sample_bill
    ):
        """Form must reject a bill that belongs to a different party and flag the bill field."""
        from ledger.forms import PaymentForm

        # sample_bill belongs to sample_vendor. We try to associate it with sample_customer.
        form = PaymentForm(
            data={
                "party": sample_customer.pk,
                "bill": sample_bill.pk,
                "amount": "250.00",
                "payment_date": timezone.now().date().strftime("%Y-%m-%d"),
                "payment_method": "cash",
            }
        )
        assert not form.is_valid()
        assert "bill" in form.errors

    def test_payment_add_view_mismatched_bill_does_not_render_raw_all_error(
        self, staff_client, sample_vendor, sample_customer, sample_bill
    ):
        """Posting mismatched bill to payment_add must not show raw '__all__:' text."""
        payload = {
            "party": sample_customer.pk,
            "bill": sample_bill.pk,
            "amount": "250.00",
            "payment_date": timezone.now().date().strftime("%Y-%m-%d"),
            "payment_method": "cash",
        }
        response = staff_client.post(self._add_payment_url(), payload)
        assert response.status_code == 400
        content = response.content.decode("utf-8")
        assert "__all__:" not in content
        assert "bill" in response.context["form"].errors
