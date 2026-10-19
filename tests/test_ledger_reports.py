"""tests/test_ledger_reports.py
==============================
QA Test-First Suite for Phase 5: Party Ledger (Khata), Spending Analytics,
Repeat Purchases & Price History, Chart Data, and CSV Exports.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from bills.models import Bill, BillItem
from categories.models import Category
from ledger.models import Payment
from parties.models import Party

User = get_user_model()


@pytest.fixture
def superadmin_user(db):
    """Create a superadmin user."""
    return User.objects.create_user(
        username="superadmin_reports",
        email="reports_admin@example.com",
        password="TestPass123!",
        role=User.Role.SUPERADMIN,
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def vendor_party(db):
    """Create a sample vendor party."""
    return Party.objects.create(
        name="Lahore Wholesale Corp",
        urdu_name="لاہور ہول سیل کارپوریشن",
        phone="03001112233",
        party_type=Party.PartyType.VENDOR,
    )


@pytest.fixture
def customer_party(db):
    """Create a sample customer party."""
    return Party.objects.create(
        name="Tariq Electronics",
        urdu_name="طارق الیکٹرانکس",
        phone="03214445566",
        party_type=Party.PartyType.CUSTOMER,
    )


@pytest.fixture
def sample_category(db):
    """Create a sample bill category."""
    return Category.objects.create(
        name="Grocery Supplies",
        urdu_name="کریانہ سامان",
        color="#10B981",
    )


@pytest.fixture
def seeded_financial_data(db, vendor_party, customer_party, sample_category, superadmin_user):
    """Seed bills, line items, and payments for financial reporting tests."""
    today = timezone.now().date()
    yesterday = today - timezone.timedelta(days=1)
    last_week = today - timezone.timedelta(days=7)

    # 1. Vendor purchase bill #1 (Unpaid, Rs 10,000)
    bill1 = Bill.objects.create(
        party=vendor_party,
        category=sample_category,
        invoice_no="BILL-001",
        bill_date=last_week,
        bill_type=Bill.BillType.PURCHASE,
        subtotal=Decimal("10000.00"),
        grand_total=Decimal("10000.00"),
        payment_status=Bill.PaymentStatus.UNPAID,
        created_by=superadmin_user,
    )
    BillItem.objects.create(
        bill=bill1,
        serial_no=1,
        item_name="Cooking Oil 16L",
        quantity=Decimal("2.000"),
        unit="tin",
        unit_price=Decimal("5000.00"),
        line_total=Decimal("10000.00"),
    )

    # 2. Vendor purchase bill #2 (Partially paid, Rs 6,000)
    bill2 = Bill.objects.create(
        party=vendor_party,
        category=sample_category,
        invoice_no="BILL-002",
        bill_date=yesterday,
        bill_type=Bill.BillType.PURCHASE,
        subtotal=Decimal("6000.00"),
        grand_total=Decimal("6000.00"),
        amount_paid=Decimal("4000.00"),
        payment_status=Bill.PaymentStatus.PARTIALLY_PAID,
        created_by=superadmin_user,
    )
    BillItem.objects.create(
        bill=bill2,
        serial_no=1,
        item_name="Cooking Oil 16L",
        quantity=Decimal("1.000"),
        unit="tin",
        unit_price=Decimal("6000.00"),  # Price increased from 5000 to 6000!
        line_total=Decimal("6000.00"),
    )

    # Record the payment for Bill #2
    Payment.objects.create(
        party=vendor_party,
        bill=bill2,
        amount=Decimal("4000.00"),
        payment_date=yesterday,
        payment_method="bank_transfer",
        reference="TXN-4000",
        created_by=superadmin_user,
    )

    # 3. Customer sale bill (Rs 8,000, Unpaid)
    bill3 = Bill.objects.create(
        party=customer_party,
        category=sample_category,
        invoice_no="SALE-001",
        bill_date=today,
        bill_type=Bill.BillType.SALE,
        subtotal=Decimal("8000.00"),
        grand_total=Decimal("8000.00"),
        payment_status=Bill.PaymentStatus.UNPAID,
        created_by=superadmin_user,
    )
    BillItem.objects.create(
        bill=bill3,
        serial_no=1,
        item_name="Cooking Oil 16L",
        quantity=Decimal("1.000"),
        unit="tin",
        unit_price=Decimal("8000.00"),
        line_total=Decimal("8000.00"),
    )

    return {
        "vendor": vendor_party,
        "customer": customer_party,
        "category": sample_category,
        "bill1": bill1,
        "bill2": bill2,
        "bill3": bill3,
    }


# ---------------------------------------------------------------------------
# 1. Party Ledger (Khata) Service Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestPartyLedgerService:
    """Verify running balance, payable/receivable categorization, and CSV export."""

    def test_vendor_ledger_running_balance_and_payable(self, seeded_financial_data):
        """Vendor ledger calculates total billed, payments, and 'You owe' balance."""
        from ledger.services import get_party_ledger_statement

        vendor = seeded_financial_data["vendor"]
        statement = get_party_ledger_statement(vendor)

        # Total purchase bills = 10,000 + 6,000 = 16,000
        assert statement["total_billed"] == Decimal("16000.00")
        # Total payments made to vendor = 4,000
        assert statement["total_paid"] == Decimal("4000.00")
        # Net balance = 16,000 - 4,000 = 12,000
        assert statement["net_balance"] == Decimal("12000.00")
        # For a vendor with positive balance, status is 'payable' ("You owe")
        assert statement["balance_type"] == "payable"
        assert "You owe" in statement["balance_label"] or "واجب الادا" in statement["balance_label"]

        # Check transactions list order and running balances
        entries = statement["entries"]
        assert len(entries) == 3  # Bill 1, Bill 2, Payment
        # First entry: Bill 1 (10,000) -> balance 10,000
        assert entries[0]["running_balance"] == Decimal("10000.00")
        # Second entry: Bill 2 (6,000) -> balance 16,000
        assert entries[1]["running_balance"] == Decimal("16000.00")
        # Third entry: Payment (4,000) -> balance 12,000
        assert entries[2]["running_balance"] == Decimal("12000.00")

    def test_customer_ledger_running_balance_and_receivable(self, seeded_financial_data):
        """Customer ledger calculates total sales, payments, and 'You will receive' balance."""
        from ledger.services import get_party_ledger_statement

        customer = seeded_financial_data["customer"]
        statement = get_party_ledger_statement(customer)

        assert statement["total_billed"] == Decimal("8000.00")
        assert statement["total_paid"] == Decimal("0.00")
        assert statement["net_balance"] == Decimal("8000.00")
        # For customer with positive balance, status is 'receivable' ("You will receive")
        assert statement["balance_type"] == "receivable"
        assert (
            "receive" in statement["balance_label"].lower() or "وصول" in statement["balance_label"]
        )

    def test_customer_linked_bill_appears_in_customer_ledger(
        self, superadmin_user, vendor_party, customer_party, sample_category
    ):
        """When a bill has a vendor party and a linked customer, it appears in both ledgers."""
        bill = Bill.objects.create(
            party=vendor_party,
            customer=customer_party,
            category=sample_category,
            invoice_no="FEE-001",
            bill_date=timezone.now().date(),
            bill_type=Bill.BillType.PURCHASE,
            subtotal=Decimal("2500.00"),
            grand_total=Decimal("2500.00"),
            payment_status=Bill.PaymentStatus.UNPAID,
            created_by=superadmin_user,
        )
        BillItem.objects.create(
            bill=bill,
            serial_no=1,
            item_name="Tuition Fee",
            quantity=Decimal("1.000"),
            unit="month",
            unit_price=Decimal("2500.00"),
            line_total=Decimal("2500.00"),
        )

        # Check customer's ledger
        from ledger.services import get_party_ledger_statement

        stmt_cust = get_party_ledger_statement(customer_party)
        assert stmt_cust["total_billed"] >= Decimal("2500.00")
        matching_entries = [e for e in stmt_cust["entries"] if e["reference"] == "FEE-001"]
        assert len(matching_entries) == 1
        assert matching_entries[0]["billed_amount"] == Decimal("2500.00")

        # Check vendor's ledger
        stmt_vend = get_party_ledger_statement(vendor_party)
        vend_entries = [e for e in stmt_vend["entries"] if e["reference"] == "FEE-001"]
        assert len(vend_entries) == 1

    def test_party_ledger_csv_export_format(self, seeded_financial_data):
        """CSV export returns attachment with formatted transactions."""
        from ledger.services import generate_ledger_csv

        vendor = seeded_financial_data["vendor"]
        csv_content = generate_ledger_csv(vendor)

        assert "Date,Type,Reference,Description,Billed,Paid,Running Balance" in csv_content
        assert "BILL-001" in csv_content
        assert "10000.00" in csv_content
        assert "TXN-4000" in csv_content


# ---------------------------------------------------------------------------
# 2. Spending Analytics & Reports Service Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestReportsServices:
    """Verify metrics calculation, category breakdowns, and date range filters."""

    def test_spending_summary_kpi_metrics(self, seeded_financial_data):
        """Spending summary computes total purchases, bill count, average bill, and outstanding credit."""
        from reports.services import get_spending_summary

        summary = get_spending_summary(date_range_key="all")

        # Total spend on purchases = 10,000 + 6,000 = 16,000
        assert summary["total_spend"] == Decimal("16000.00")
        assert summary["purchase_bills_count"] == 2
        # Average bill = 16,000 / 2 = 8,000
        assert summary["average_bill"] == Decimal("8000.00")
        # Outstanding credit = (10,000 unpaid) + (2,000 remaining on bill 2) = 12,000
        assert summary["outstanding_credit"] == Decimal("12000.00")
        assert summary["top_vendor"] == "Lahore Wholesale Corp"

    def test_spending_by_category_aggregation(self, seeded_financial_data):
        """Breakdown aggregates total spent per category with percentage."""
        from reports.services import get_spending_by_category

        breakdown = get_spending_by_category()
        assert len(breakdown) >= 1
        grocery = next(c for c in breakdown if c["name"] == "Grocery Supplies")
        assert grocery["total_amount"] == Decimal("16000.00")
        assert grocery["color"] == "#10B981"
        assert grocery["percentage"] == 100.0

    def test_top_vendors_ranking(self, seeded_financial_data):
        """Top vendors returns list sorted by total spend descending."""
        from reports.services import get_top_vendors

        top_vendors = get_top_vendors(limit=5)
        assert len(top_vendors) >= 1
        assert top_vendors[0]["name"] == "Lahore Wholesale Corp"
        assert top_vendors[0]["total_spent"] == Decimal("16000.00")

    def test_spending_over_time_chart_data(self, seeded_financial_data):
        """Spending over time formats chronological intervals for Chart.js."""
        from reports.services import get_spending_over_time

        chart_data = get_spending_over_time(interval="day")
        assert "labels" in chart_data
        assert "data" in chart_data
        assert len(chart_data["labels"]) == len(chart_data["data"])
        assert sum(chart_data["data"]) == 16000.0


# ---------------------------------------------------------------------------
# 3. Repeat Purchases & Item Price History Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestPriceHistoryTracking:
    """Verify tracking item price fluctuations across multiple bills over time."""

    def test_item_price_history_detects_inflation(self, seeded_financial_data):
        """Item 'Cooking Oil 16L' tracks price increase from 5,000 to 6,000."""
        from reports.services import get_item_price_history

        history_report = get_item_price_history(item_name="Cooking Oil 16L")
        assert history_report["item_name"] == "Cooking Oil 16L"
        assert history_report["min_price"] == Decimal("5000.00")
        assert history_report["max_price"] == Decimal("6000.00")
        assert history_report["latest_price"] == Decimal("6000.00")
        # Price increased by +20% (from 5000 to 6000)
        assert history_report["percent_change"] == Decimal("20.00")
        assert history_report["trend"] == "increased"

    def test_all_items_price_index(self, seeded_financial_data):
        """Price index returns summary table of all repeat items."""
        from reports.services import get_all_items_price_summary

        items_summary = get_all_items_price_summary()
        assert len(items_summary) >= 1
        oil_item = next(it for it in items_summary if "Cooking Oil" in it["name"])
        assert oil_item["purchase_count"] == 2
        assert oil_item["latest_price"] == Decimal("6000.00")


# ---------------------------------------------------------------------------
# 4. Views & Endpoints Integration Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestLedgerAndReportsViews:
    """Verify HTTP endpoints, CSV downloads, permissions, and templates."""

    def test_dashboard_view_renders_live_metrics_and_charts(
        self, client, superadmin_user, seeded_financial_data
    ):
        """Dashboard renders live KPI stats, Chart.js canvas elements, and pending balances."""
        client.force_login(superadmin_user)
        response = client.get("/en/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")

        # Live stats
        assert "16,000" in content or "16000" in content
        assert "12,000" in content or "12000" in content
        # Chart.js scripts & canvases
        assert "chart.js" in content.lower() or "canvas" in content.lower()

    def test_party_ledger_view_renders_statement(
        self, client, superadmin_user, seeded_financial_data
    ):
        """Party ledger view renders statement with running balance table."""
        client.force_login(superadmin_user)
        vendor = seeded_financial_data["vendor"]

        response = client.get(f"/en/ledger/party/{vendor.pk}/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert vendor.name in content
        assert "BILL-001" in content
        assert "12,000" in content or "12000" in content

    def test_party_ledger_csv_export_endpoint(self, client, superadmin_user, seeded_financial_data):
        """GET /en/ledger/party/<id>/export/csv/ downloads CSV file."""
        client.force_login(superadmin_user)
        vendor = seeded_financial_data["vendor"]

        response = client.get(f"/en/ledger/party/{vendor.pk}/export/csv/")
        assert response.status_code == 200
        assert "text/csv" in response["Content-Type"]
        assert 'attachment; filename="ledger-' in response["Content-Disposition"]
        assert b"BILL-001" in response.content

    def test_spending_report_view(self, client, superadmin_user, seeded_financial_data):
        """Spending report view renders category breakdown and date filters."""
        client.force_login(superadmin_user)

        response = client.get("/en/reports/spending/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Spending Reports" in content or "Spending" in content
        assert "Grocery Supplies" in content

    def test_price_history_view(self, client, superadmin_user, seeded_financial_data):
        """Price history view renders table of tracked items."""
        client.force_login(superadmin_user)

        response = client.get("/en/reports/price-history/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Price History" in content or "Price" in content
        assert "Cooking Oil 16L" in content

    def test_reports_views_bilingual_rtl_and_dark_mode(
        self, client, superadmin_user, seeded_financial_data
    ):
        """Reports and ledger render in Urdu (RTL) with dark mode classes."""
        client.force_login(superadmin_user)
        vendor = seeded_financial_data["vendor"]

        # Urdu Ledger
        response_ur = client.get(f"/ur/ledger/party/{vendor.pk}/")
        assert response_ur.status_code == 200
        content_ur = response_ur.content.decode("utf-8")
        assert 'dir="rtl"' in content_ur
        assert "dark:bg-slate-800" in content_ur

        # Urdu Spending
        response_spend_ur = client.get("/ur/reports/spending/")
        assert response_spend_ur.status_code == 200
        assert 'dir="rtl"' in response_spend_ur.content.decode("utf-8")

    def test_export_spending_csv_endpoint(self, client, superadmin_user, seeded_financial_data):
        """Test GET /en/reports/spending/export/csv/ downloads spending CSV."""
        client.force_login(superadmin_user)
        response = client.get("/en/reports/spending/export/csv/")
        assert response.status_code == 200
        assert "text/csv" in response["Content-Type"]
        assert 'attachment; filename="spending-report-' in response["Content-Disposition"]
        assert b"BILL-001" in response.content

    def test_price_history_item_query_view(self, client, superadmin_user, seeded_financial_data):
        """Test GET /en/reports/price-history/?item=Cooking+Oil+16L renders detail."""
        client.force_login(superadmin_user)
        response = client.get("/en/reports/price-history/?item=Cooking Oil 16L")
        assert response.status_code == 200
        assert b"Cooking Oil 16L" in response.content


@pytest.mark.django_db
class TestReportsServicesEdgeCases:
    """Comprehensive boundary and edge cases for reports and ledger services."""

    def test_get_date_range_all_presets(self):
        """Verify all date range presets and custom string date parsing."""
        from reports.services import get_date_range

        today = timezone.now().date()

        # today
        assert get_date_range("today") == (today, today)
        # yesterday
        yest = today - timezone.timedelta(days=1)
        assert get_date_range("yesterday") == (yest, yest)
        # this_week
        start_week, end_week = get_date_range("this_week")
        assert end_week == today
        assert start_week <= today
        # this_month
        start_month, end_month = get_date_range("this_month")
        assert end_month == today
        assert start_month.day == 1
        # this_year
        start_year, end_year = get_date_range("this_year")
        assert end_year == today
        assert start_year.month == 1 and start_year.day == 1
        # custom with valid dates
        assert get_date_range("custom", "2026-01-01", "2026-01-31") == (
            timezone.datetime(2026, 1, 1).date(),
            timezone.datetime(2026, 1, 31).date(),
        )
        # custom with invalid dates
        assert get_date_range("custom", "invalid", "bad") == (None, None)
        # all
        assert get_date_range("all") == (None, None)

    def test_spending_summary_with_custom_date_bounds(self, seeded_financial_data):
        """Verify date filters constrain spending metrics correctly."""
        from reports.services import get_spending_summary

        today = timezone.now().date()

        # Filter strictly for today: only bill3 exists (sale, not purchase), so 0 purchase spend
        summary_today = get_spending_summary(date_range_key="today")
        assert summary_today["total_spend"] == Decimal("0.00")
        assert summary_today["purchase_bills_count"] == 0

        # Filter with custom range covering yesterday
        yest = today - timezone.timedelta(days=1)
        summary_yest = get_spending_summary(
            date_range_key="custom", custom_start=str(yest), custom_end=str(yest)
        )
        assert summary_yest["total_spend"] == Decimal("6000.00")
        assert summary_yest["purchase_bills_count"] == 1

    def test_spending_by_category_and_vendors_with_date_filters(self, seeded_financial_data):
        """Verify date filters work for category and vendor breakdowns."""
        from reports.services import (
            get_spending_by_category,
            get_spending_over_time,
            get_top_vendors,
        )

        today = timezone.now().date()
        yest = today - timezone.timedelta(days=1)

        cats = get_spending_by_category(start_date=yest, end_date=yest)
        assert len(cats) == 1
        assert cats[0]["total_amount"] == Decimal("6000.00")

        vendors = get_top_vendors(limit=5, start_date=yest, end_date=yest)
        assert len(vendors) == 1
        assert vendors[0]["total_spent"] == Decimal("6000.00")

        timeline = get_spending_over_time(start_date=yest, end_date=yest)
        assert len(timeline["labels"]) == 1
        assert timeline["data"][0] == 6000.0

    def test_generate_spending_csv(self, seeded_financial_data):
        """Verify generate_spending_csv produces expected headers and rows."""
        from reports.services import generate_spending_csv

        csv_out = generate_spending_csv()
        assert (
            "Invoice No,Date,Vendor,Category,Subtotal,Discount,Tax,Grand Total,Amount Paid,Status"
            in csv_out
        )
        assert "BILL-001" in csv_out
        assert "10000.00" in csv_out

    def test_item_price_history_not_found_and_price_decrease(
        self, db, superadmin_user, vendor_party
    ):
        """Verify get_item_price_history for nonexistent item, and for price decrease."""
        from reports.services import get_item_price_history

        # Not found
        empty_res = get_item_price_history("Nonexistent Item 12345")
        assert empty_res["min_price"] == Decimal("0.00")
        assert empty_res["trend"] == "stable"

        # Price decrease scenario
        today = timezone.now().date()
        bill_a = Bill.objects.create(
            party=vendor_party,
            invoice_no="DEC-001",
            bill_date=today - timezone.timedelta(days=2),
            bill_type=Bill.BillType.PURCHASE,
            subtotal=Decimal("1000.00"),
            grand_total=Decimal("1000.00"),
            created_by=superadmin_user,
        )
        BillItem.objects.create(
            bill=bill_a,
            serial_no=1,
            item_name="Detergent 5kg",
            quantity=Decimal("1.000"),
            unit="bag",
            unit_price=Decimal("1000.00"),
            line_total=Decimal("1000.00"),
        )

        bill_b = Bill.objects.create(
            party=vendor_party,
            invoice_no="DEC-002",
            bill_date=today,
            bill_type=Bill.BillType.PURCHASE,
            subtotal=Decimal("800.00"),
            grand_total=Decimal("800.00"),
            created_by=superadmin_user,
        )
        BillItem.objects.create(
            bill=bill_b,
            serial_no=1,
            item_name="Detergent 5kg",
            quantity=Decimal("1.000"),
            unit="bag",
            unit_price=Decimal("800.00"),
            line_total=Decimal("800.00"),
        )

        res = get_item_price_history("Detergent 5kg")
        assert res["trend"] == "decreased"
        assert res["percent_change"] == Decimal("-20.00")

    def test_ledger_statement_advance_and_settled_states(self, db, superadmin_user):
        """Verify ledger statement handles advance payments and perfectly settled balances."""
        from ledger.services import get_party_ledger_statement, record_payment

        cust = Party.objects.create(name="Advance Customer", party_type=Party.PartyType.CUSTOMER)
        vend = Party.objects.create(name="Settled Vendor", party_type=Party.PartyType.VENDOR)

        # 1. Customer advance payment (Paid 5000 without bill) -> net balance -5000 -> "advance"
        record_payment(party=cust, amount=Decimal("5000.00"), created_by=superadmin_user)
        cust_stmt = get_party_ledger_statement(cust)
        assert cust_stmt["balance_type"] == "advance"
        assert (
            "Advance received" in cust_stmt["balance_label"]
            or "پیشگی" in cust_stmt["balance_label"]
        )

        # 2. Customer settled account
        Bill.objects.create(
            party=cust,
            bill_type=Bill.BillType.SALE,
            subtotal=Decimal("5000.00"),
            grand_total=Decimal("5000.00"),
            created_by=superadmin_user,
        )
        cust_stmt_settled = get_party_ledger_statement(cust)
        assert cust_stmt_settled["balance_type"] == "settled"

        # 3. Vendor advance payment (Overpaid) -> net balance < 0 -> "advance"
        record_payment(party=vend, amount=Decimal("3000.00"), created_by=superadmin_user)
        vend_stmt = get_party_ledger_statement(vend)
        assert vend_stmt["balance_type"] == "advance"
        assert "Advance paid" in vend_stmt["balance_label"] or "پیشگی" in vend_stmt["balance_label"]

        # 4. Vendor settled account
        Bill.objects.create(
            party=vend,
            bill_type=Bill.BillType.PURCHASE,
            subtotal=Decimal("3000.00"),
            grand_total=Decimal("3000.00"),
            created_by=superadmin_user,
        )
        vend_stmt_settled = get_party_ledger_statement(vend)
        assert vend_stmt_settled["balance_type"] == "settled"


class TestIncorrectBillsReport:
    """Test suite for incorrect & discrepant bills reporting, filters, and CSV exports."""

    def test_incorrect_bills_report_service(
        self, db, superadmin_user, vendor_party, customer_party
    ):
        from reports.services import generate_incorrect_bills_csv, get_incorrect_bills_report

        # 1. Correct bill (should not appear)
        Bill.objects.create(
            party=vendor_party,
            invoice_no="INV-OK-01",
            subtotal=Decimal("100.00"),
            grand_total=Decimal("100.00"),
            has_discrepancy=False,
            created_by=superadmin_user,
        )

        # 2. Incorrect vendor bill with discrepancy
        b_vend = Bill.objects.create(
            party=vendor_party,
            invoice_no="INV-ERR-VEND",
            subtotal=Decimal("2670.00"),
            grand_total=Decimal("2670.00"),
            original_slip_total=Decimal("2670.00"),
            has_discrepancy=True,
            discrepancy_reason="Customer handwritten slip PKR 2670 differs from items sum PKR 2676",
            created_by=superadmin_user,
        )
        BillItem.objects.create(
            bill=b_vend,
            serial_no=1,
            item_name="Rice Basmati",
            quantity=Decimal("2.000"),
            unit="kg",
            unit_price=Decimal("1338.00"),
            line_total=Decimal("2676.00"),
        )

        # 3. Incorrect customer bill
        b_cust = Bill.objects.create(
            party=customer_party,
            invoice_no="INV-ERR-CUST",
            subtotal=Decimal("500.00"),
            grand_total=Decimal("500.00"),
            original_slip_total=Decimal("500.00"),
            has_discrepancy=True,
            discrepancy_reason="Line total math mismatch",
            created_by=superadmin_user,
        )
        BillItem.objects.create(
            bill=b_cust,
            serial_no=1,
            item_name="Oil Can",
            quantity=Decimal("1.000"),
            unit="can",
            unit_price=Decimal("550.00"),
            line_total=Decimal("550.00"),
        )

        # 4. Corrected/Resolved bill (previously had discrepancy, now corrected)
        b_resolved = Bill.objects.create(
            party=vendor_party,
            invoice_no="INV-RESOLVED-01",
            subtotal=Decimal("1500.00"),
            grand_total=Decimal("1500.00"),
            original_slip_total=Decimal("1400.00"),
            has_discrepancy=False,
            had_discrepancy=True,
            discrepancy_resolved=True,
            discrepancy_resolved_at=timezone.now(),
            discrepancy_reason="Corrected on 2026-10-14: Previously recorded with paper slip PKR 1400.00. Corrected to actual items sum PKR 1500.00.",
            created_by=superadmin_user,
        )
        BillItem.objects.create(
            bill=b_resolved,
            serial_no=1,
            item_name="Sugar",
            quantity=Decimal("10.000"),
            unit="kg",
            unit_price=Decimal("150.00"),
            line_total=Decimal("1500.00"),
        )

        # Test all parties (includes both unresolved and resolved)
        all_rep = get_incorrect_bills_report(party_type="all", resolution_status="all")
        assert all_rep["total_count"] == 3
        assert all_rep["unresolved_count"] == 2
        assert all_rep["resolved_count"] == 1
        assert all_rep["vendor_count"] == 2
        assert all_rep["customer_count"] == 1

        # Test resolution_status="unresolved"
        unresolved_rep = get_incorrect_bills_report(
            party_type="all", resolution_status="unresolved"
        )
        assert unresolved_rep["total_count"] == 2
        invoices_unresolved = [r["invoice_no"] for r in unresolved_rep["records"]]
        assert "INV-ERR-VEND" in invoices_unresolved
        assert "INV-ERR-CUST" in invoices_unresolved
        assert "INV-RESOLVED-01" not in invoices_unresolved

        # Test resolution_status="resolved"
        resolved_rep = get_incorrect_bills_report(party_type="all", resolution_status="resolved")
        assert resolved_rep["total_count"] == 1
        assert resolved_rep["records"][0]["invoice_no"] == "INV-RESOLVED-01"
        assert resolved_rep["records"][0]["discrepancy_resolved"] is True

        # Test vendor filter
        vend_rep = get_incorrect_bills_report(party_type="vendor", resolution_status="all")
        assert vend_rep["total_count"] == 2

        # Test customer filter
        cust_rep = get_incorrect_bills_report(party_type="customer", resolution_status="all")
        assert cust_rep["total_count"] == 1
        assert cust_rep["records"][0]["invoice_no"] == "INV-ERR-CUST"

        # Test party_id filter
        specific_rep = get_incorrect_bills_report(party_id=vendor_party.pk, resolution_status="all")
        assert specific_rep["total_count"] == 2

        # Test CSV export
        csv_out = generate_incorrect_bills_csv(party_type="all", resolution_status="all")
        assert "INV-ERR-VEND" in csv_out
        assert "INV-ERR-CUST" in csv_out
        assert "INV-RESOLVED-01" in csv_out
        assert "Corrected" in csv_out
        assert "Unresolved" in csv_out
        assert "INV-OK-01" not in csv_out

    def test_incorrect_bills_views(self, client, db, superadmin_user, vendor_party):
        from django.urls import reverse

        client.force_login(superadmin_user)

        # Create active discrepant bill
        Bill.objects.create(
            party=vendor_party,
            invoice_no="INV-VIEW-01",
            subtotal=Decimal("1000.00"),
            grand_total=Decimal("1000.00"),
            original_slip_total=Decimal("1000.00"),
            has_discrepancy=True,
            discrepancy_reason="Test discrepancy",
            created_by=superadmin_user,
        )

        # Create resolved bill
        Bill.objects.create(
            party=vendor_party,
            invoice_no="INV-VIEW-RESOLVED",
            subtotal=Decimal("1200.00"),
            grand_total=Decimal("1200.00"),
            original_slip_total=Decimal("1100.00"),
            has_discrepancy=False,
            had_discrepancy=True,
            discrepancy_resolved=True,
            discrepancy_resolved_at=timezone.now(),
            discrepancy_reason="Corrected to actual items sum",
            created_by=superadmin_user,
        )

        # Report view - default (all)
        resp = client.get(reverse("reports:incorrect_bills"))
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "INV-VIEW-01" in content
        assert "INV-VIEW-RESOLVED" in content
        assert "Discrepant Bills" in content

        # Filter by resolution=unresolved
        resp_unresolved = client.get(reverse("reports:incorrect_bills") + "?resolution=unresolved")
        assert resp_unresolved.status_code == 200
        content_unres = resp_unresolved.content.decode("utf-8")
        assert "INV-VIEW-01" in content_unres
        assert "INV-VIEW-RESOLVED" not in content_unres

        # Filter by resolution=resolved
        resp_res = client.get(reverse("reports:incorrect_bills") + "?resolution=resolved")
        assert resp_res.status_code == 200
        content_res = resp_res.content.decode("utf-8")
        assert "INV-VIEW-RESOLVED" in content_res
        assert "INV-VIEW-01" not in content_res

        # Filter by customer (empty result)
        resp_cust = client.get(reverse("reports:incorrect_bills") + "?party_type=customer")
        assert resp_cust.status_code == 200
        assert "No Incorrect or Discrepant Bills Found" in resp_cust.content.decode("utf-8")

        # CSV export with resolution filter
        resp_csv = client.get(reverse("reports:incorrect_bills_csv") + "?resolution=resolved")
        assert resp_csv.status_code == 200
        assert resp_csv["Content-Type"].startswith("text/csv")
        csv_body = resp_csv.content.decode("utf-8")
        assert "INV-VIEW-RESOLVED" in csv_body
        assert "INV-VIEW-01" not in csv_body

    def test_ledger_dashboard_view(self, client, superadmin_user, vendor_party, customer_party):
        """Test ledger general dashboard renders with metrics and filters."""
        client.force_login(superadmin_user)

        # Create active bills for vendor and customer
        bill_v = Bill.objects.create(
            party=vendor_party,
            invoice_no="INV-VEND-1",
            grand_total=Decimal("5000.00"),
            payment_status=Bill.PaymentStatus.PARTIALLY_PAID,
            created_by=superadmin_user,
        )
        Payment.objects.create(
            party=vendor_party,
            bill=bill_v,
            amount=Decimal("2000.00"),
            payment_method=Payment.PaymentMethod.CASH,
            created_by=superadmin_user,
        )
        Bill.objects.create(
            party=customer_party,
            invoice_no="INV-CUST-1",
            grand_total=Decimal("3000.00"),
            payment_status=Bill.PaymentStatus.UNPAID,
            created_by=superadmin_user,
        )

        resp = client.get(reverse("ledger:ledger_dashboard"))
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "General Ledger" in content
        assert "Lahore Wholesale Corp" in content
        assert "Tariq Electronics" in content
        assert "Total Receivable" in content
        assert "Total Payable" in content

        # Test filter by vendor
        resp_vendor = client.get(reverse("ledger:ledger_dashboard") + "?type=vendor")
        assert resp_vendor.status_code == 200
        content_vendor = resp_vendor.content.decode("utf-8")
        assert "Lahore Wholesale Corp" in content_vendor
        assert "Tariq Electronics" not in content_vendor

        # Test filter by customer
        resp_cust = client.get(reverse("ledger:ledger_dashboard") + "?type=customer")
        assert resp_cust.status_code == 200
        content_cust = resp_cust.content.decode("utf-8")
        assert "Tariq Electronics" in content_cust
        assert "Lahore Wholesale Corp" not in content_cust
