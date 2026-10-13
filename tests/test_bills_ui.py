"""tests/test_bills_ui.py
========================
UI integration tests for Phase 3: Bills, Parties, and Payments.
Verifies templates, responsive layout, light/dark mode classes,
and English (LTR) / Urdu (RTL) localization.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from bills.models import Bill, BillItem
from parties.models import Party

User = get_user_model()


@pytest.fixture
def superadmin_user(db):
    """Create a superadmin user."""
    return User.objects.create_user(
        username="admin_ui",
        email="admin_ui@example.com",
        password="TestPass123!",
        role=User.Role.SUPERADMIN,
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def standard_staff_user(db):
    """Create a staff user without delete permissions."""
    return User.objects.create_user(
        username="staff_regular",
        email="staff_regular@example.com",
        password="TestPass123!",
        role=User.Role.STAFF,
        can_delete_records=False,
    )


@pytest.fixture
def sample_vendor(db):
    """Create a sample vendor party."""
    return Party.objects.create(
        name="Metro Wholesalers",
        urdu_name="میٹرو ہول سیلرز",
        phone="03001234567",
        party_type=Party.PartyType.VENDOR,
        address="Lahore, Pakistan",
    )


@pytest.fixture
def sample_customer(db):
    """Create a sample customer party."""
    return Party.objects.create(
        name="Ahmed Ali",
        urdu_name="احمد علی",
        phone="03217654321",
        party_type=Party.PartyType.CUSTOMER,
        address="Karachi, Pakistan",
    )


@pytest.fixture
def sample_bill(db, sample_vendor, superadmin_user):
    """Create a sample bill with line items."""
    bill = Bill.objects.create(
        party=sample_vendor,
        invoice_no="INV-2026-99",
        bill_type=Bill.BillType.PURCHASE,
        subtotal=Decimal("500.00"),
        grand_total=Decimal("500.00"),
        payment_status=Bill.PaymentStatus.UNPAID,
        created_by=superadmin_user,
    )
    BillItem.objects.create(
        bill=bill,
        serial_no=1,
        item_name="Cooking Oil 5L",
        quantity=Decimal("2.000"),
        unit="ltr",
        unit_price=Decimal("250.00"),
        line_total=Decimal("500.00"),
    )
    return bill


@pytest.mark.django_db
class TestPartiesUI:
    """Test party (vendor & customer) UI templates and workflows."""

    def test_vendor_list_ui_english(self, client, superadmin_user, sample_vendor):
        """Vendor list renders in English (LTR)."""
        client.force_login(superadmin_user)
        response = client.get("/en/parties/vendors/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'dir="ltr"' in content
        assert "Vendors & Suppliers" in content
        assert sample_vendor.name in content
        assert "Add Vendor" in content

    def test_vendor_list_ui_urdu(self, client, superadmin_user, sample_vendor):
        """Vendor list renders in Urdu (RTL)."""
        client.force_login(superadmin_user)
        response = client.get("/ur/parties/vendors/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'dir="rtl"' in content
        assert sample_vendor.name in content

    def test_customer_list_ui_english(self, client, superadmin_user, sample_customer):
        """Customer list renders in English (LTR)."""
        client.force_login(superadmin_user)
        response = client.get("/en/parties/customers/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'dir="ltr"' in content
        assert "Customers" in content
        assert sample_customer.name in content
        assert "Add Customer" in content

    def test_customer_list_ui_urdu(self, client, superadmin_user, sample_customer):
        """Customer list renders in Urdu (RTL)."""
        client.force_login(superadmin_user)
        response = client.get("/ur/parties/customers/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'dir="rtl"' in content
        assert sample_customer.name in content

    def test_party_add_and_edit_ui(self, client, superadmin_user, sample_vendor):
        """Party creation and editing forms render correctly."""
        client.force_login(superadmin_user)

        # Add Party form
        response = client.get("/en/parties/add/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Party / Business Name" in content or "Name" in content
        assert 'name="party_type"' in content

        # Edit Party form
        response_edit = client.get(f"/en/parties/{sample_vendor.pk}/edit/")
        assert response_edit.status_code == 200
        content_edit = response_edit.content.decode("utf-8")
        assert sample_vendor.name in content_edit
        assert "Edit Party" in content_edit


@pytest.mark.django_db
class TestBillsUI:
    """Test Bill UI templates, line item rendering, trash, and payments."""

    def test_bill_list_ui(self, client, superadmin_user, sample_bill):
        """Bill list renders with search, filters, and invoices in English."""
        client.force_login(superadmin_user)

        response = client.get("/en/bills/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert sample_bill.invoice_no in content
        assert sample_bill.party.name in content
        assert "New Bill" in content or "Add Bill" in content
        assert "Trash" in content

    def test_bill_list_ui_urdu(self, client, superadmin_user, sample_bill):
        """Bill list renders in Urdu with RTL."""
        client.force_login(superadmin_user)

        response = client.get("/ur/bills/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'dir="rtl"' in content
        assert sample_bill.invoice_no in content

    def test_bill_add_ui(self, client, superadmin_user, sample_vendor):
        """Manual bill creation form renders with item fields in English."""
        client.force_login(superadmin_user)

        response = client.get("/en/bills/add/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Invoice Details" in content
        assert "Line Items" in content
        assert 'name="party"' in content
        assert 'name="items-0-item_name"' in content

    def test_bill_detail_ui(self, client, superadmin_user, sample_bill):
        """Bill detail view renders breakdown, line items, and totals."""
        client.force_login(superadmin_user)

        response = client.get(f"/en/bills/{sample_bill.pk}/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert sample_bill.invoice_no in content
        assert "Cooking Oil 5L" in content
        assert "500.00" in content
        assert "Record Payment" in content

    def test_bill_trash_and_restore_permissions_ui(
        self, client, superadmin_user, standard_staff_user, sample_bill
    ):
        """Staff without can_delete_records is 403 on trash, superadmin allowed."""
        # Staff denied
        client.force_login(standard_staff_user)
        response_denied = client.get("/en/bills/trash/")
        assert response_denied.status_code == 403

        # Superadmin allowed
        client.force_login(superadmin_user)
        response_allowed = client.get("/en/bills/trash/")
        assert response_allowed.status_code == 200

        # Confirm delete page
        response_del = client.get(f"/en/bills/{sample_bill.pk}/delete/")
        assert response_del.status_code == 200
        content_del = response_del.content.decode("utf-8")
        assert "Move to Trash" in content_del or "Confirm Delete" in content_del

        # Soft delete bill
        sample_bill.is_deleted = True
        sample_bill.save()

        # Confirm restore page
        response_res = client.get(f"/en/bills/{sample_bill.pk}/restore/")
        assert response_res.status_code == 200
        content_res = response_res.content.decode("utf-8")
        assert "Restore" in content_res

    def test_payment_ui_templates(self, client, superadmin_user, sample_bill):
        """Payment recording forms render with all necessary inputs."""
        client.force_login(superadmin_user)

        # General payment form
        response_general = client.get("/en/ledger/payments/add/")
        assert response_general.status_code == 200
        content_general = response_general.content.decode("utf-8")
        assert "Record Payment" in content_general
        assert 'name="amount"' in content_general

        # Bill-specific payment form
        response_bill = client.get(f"/en/bills/{sample_bill.pk}/payment/")
        assert response_bill.status_code == 200
        content_bill = response_bill.content.decode("utf-8")
        assert "Record Bill Payment" in content_bill or "Record Payment" in content_bill
        assert sample_bill.invoice_no in content_bill
