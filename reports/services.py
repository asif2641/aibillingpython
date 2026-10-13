"""reports/services.py
===================
Business logic for financial analytics, spending summaries, category breakdowns,
vendor rankings, price history tracking, and CSV exports.
"""

import csv
import datetime
import io
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from django.db.models import Count, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext as _

from billing.utils import money_round
from bills.models import Bill, BillItem


def get_date_range(
    filter_key: str = "all",
    custom_start: datetime.date | str | None = None,
    custom_end: datetime.date | str | None = None,
) -> Tuple[datetime.date | None, datetime.date | None]:
    """Calculate date range bounds based on filter preset or custom dates.

    Supported keys: 'all', 'today', 'yesterday', 'this_week', 'this_month', 'this_year', 'custom'.
    """
    today = timezone.now().date()

    if filter_key == "today":
        return today, today
    if filter_key == "yesterday":
        yest = today - datetime.timedelta(days=1)
        return yest, yest
    if filter_key == "this_week":
        start_of_week = today - datetime.timedelta(days=today.weekday())
        return start_of_week, today
    if filter_key == "this_month":
        start_of_month = today.replace(day=1)
        return start_of_month, today
    if filter_key == "this_year":
        start_of_year = today.replace(month=1, day=1)
        return start_of_year, today
    if filter_key == "custom":
        start = custom_start
        end = custom_end
        if isinstance(start, str) and start.strip():
            try:
                start = datetime.date.fromisoformat(start.strip())
            except ValueError:
                start = None
        if isinstance(end, str) and end.strip():
            try:
                end = datetime.date.fromisoformat(end.strip())
            except ValueError:
                end = None
        return start, end
    # "all" or unknown
    return None, None


def get_spending_summary(
    date_range_key: str = "all",
    custom_start=None,
    custom_end=None,
) -> Dict[str, Any]:
    """Calculate high-level spending KPIs for purchase bills."""
    start_date, end_date = get_date_range(date_range_key, custom_start, custom_end)

    bills = Bill.objects.filter(is_deleted=False, bill_type=Bill.BillType.PURCHASE)
    if start_date:
        bills = bills.filter(bill_date__gte=start_date)
    if end_date:
        bills = bills.filter(bill_date__lte=end_date)

    aggregates = bills.aggregate(
        total_spend=Coalesce(Sum("grand_total"), Decimal("0.00")),
        total_paid=Coalesce(Sum("amount_paid"), Decimal("0.00")),
        count=Count("id"),
    )

    total_spend = money_round(aggregates["total_spend"])
    purchase_bills_count = aggregates["count"]

    if purchase_bills_count > 0:
        average_bill = money_round(total_spend / Decimal(str(purchase_bills_count)))
    else:
        average_bill = Decimal("0.00")

    credit_agg = bills.filter(grand_total__gt=F("amount_paid")).aggregate(
        total_credit=Coalesce(Sum(F("grand_total") - F("amount_paid")), Decimal("0.00"))
    )
    outstanding_credit = money_round(credit_agg["total_credit"])

    top_vendor_row = (
        bills.filter(party__isnull=False)
        .values("party__name")
        .annotate(total_vendor_spent=Sum("grand_total"))
        .order_by("-total_vendor_spent")
        .first()
    )
    top_vendor = top_vendor_row["party__name"] if top_vendor_row else ""

    return {
        "total_spend": total_spend,
        "purchase_bills_count": purchase_bills_count,
        "average_bill": average_bill,
        "outstanding_credit": outstanding_credit,
        "top_vendor": top_vendor,
    }


def get_spending_by_category(start_date=None, end_date=None) -> List[Dict[str, Any]]:
    """Aggregate spending by expense category with percentages."""
    bills = Bill.objects.filter(is_deleted=False, bill_type=Bill.BillType.PURCHASE)
    if start_date:
        bills = bills.filter(bill_date__gte=start_date)
    if end_date:
        bills = bills.filter(bill_date__lte=end_date)

    grouped = (
        bills.values("category__id", "category__name", "category__urdu_name", "category__color")
        .annotate(total_amount=Sum("grand_total"))
        .order_by("-total_amount")
    )

    total_across = sum((row["total_amount"] or Decimal("0.00")) for row in grouped)

    result = []
    for row in grouped:
        amt = money_round(row["total_amount"] or Decimal("0.00"))
        if total_across > Decimal("0.00"):
            pct = round(float((amt / total_across) * Decimal("100")), 2)
        else:
            pct = 0.0

        name = row["category__name"] or _("Uncategorized")
        urdu_name = row["category__urdu_name"] or "دیگر"
        color = row["category__color"] or "#64748B"

        result.append(
            {
                "category_id": row["category__id"],
                "name": name,
                "urdu_name": urdu_name,
                "color": color,
                "total_amount": amt,
                "percentage": pct,
            }
        )

    return result


def get_top_vendors(
    limit: int = 10,
    start_date=None,
    end_date=None,
) -> List[Dict[str, Any]]:
    """Aggregate purchase bills by vendor and rank by total spent."""
    bills = Bill.objects.filter(
        is_deleted=False, bill_type=Bill.BillType.PURCHASE, party__isnull=False
    )
    if start_date:
        bills = bills.filter(bill_date__gte=start_date)
    if end_date:
        bills = bills.filter(bill_date__lte=end_date)

    vendor_grouped = (
        bills.values("party__id", "party__name", "party__urdu_name", "party__phone")
        .annotate(
            total_spent=Sum("grand_total"),
            bill_count=Count("id"),
        )
        .order_by("-total_spent")[:limit]
    )

    results = []
    for row in vendor_grouped:
        results.append(
            {
                "party_id": row["party__id"],
                "name": row["party__name"],
                "urdu_name": row["party__urdu_name"],
                "phone": row["party__phone"],
                "total_spent": money_round(row["total_spent"] or Decimal("0.00")),
                "bill_count": row["bill_count"],
            }
        )

    return results


def get_spending_over_time(
    interval: str = "day",
    start_date=None,
    end_date=None,
) -> Dict[str, Any]:
    """Format chronological interval data for Chart.js."""
    bills = Bill.objects.filter(is_deleted=False, bill_type=Bill.BillType.PURCHASE)
    if start_date:
        bills = bills.filter(bill_date__gte=start_date)
    if end_date:
        bills = bills.filter(bill_date__lte=end_date)

    daily = bills.values("bill_date").annotate(total=Sum("grand_total")).order_by("bill_date")

    labels: List[str] = []
    data: List[float] = []

    for row in daily:
        labels.append(row["bill_date"].strftime("%Y-%m-%d"))
        data.append(float(money_round(row["total"] or Decimal("0.00"))))

    return {
        "labels": labels,
        "data": data,
    }


def get_item_price_history(item_name: str) -> Dict[str, Any]:
    """Track item purchase price fluctuations chronologically."""
    items_qs = (
        BillItem.objects.filter(
            item_name__iexact=item_name,
            bill__is_deleted=False,
            bill__bill_type=Bill.BillType.PURCHASE,
        )
        .select_related("bill", "bill__party")
        .order_by("bill__bill_date", "bill__id", "id")
    )

    items = list(items_qs)
    if not items:
        return {
            "item_name": item_name,
            "min_price": Decimal("0.00"),
            "max_price": Decimal("0.00"),
            "latest_price": Decimal("0.00"),
            "percent_change": Decimal("0.00"),
            "trend": "stable",
            "history": [],
        }

    prices = [it.unit_price for it in items]
    min_price = money_round(min(prices))
    max_price = money_round(max(prices))
    first_price = prices[0]
    latest_price = money_round(prices[-1])

    if first_price > Decimal("0.00"):
        percent_change = money_round(((latest_price - first_price) / first_price) * Decimal("100"))
    else:
        percent_change = Decimal("0.00")

    if latest_price > first_price:
        trend = "increased"
    elif latest_price < first_price:
        trend = "decreased"
    else:
        trend = "stable"

    history = []
    for it in items:
        history.append(
            {
                "bill_id": it.bill_id,
                "invoice_no": it.bill.invoice_no or f"BILL-{it.bill_id}",
                "bill_date": it.bill.bill_date,
                "party_name": it.bill.party.name if it.bill.party else "",
                "quantity": it.quantity,
                "unit": it.unit,
                "unit_price": money_round(it.unit_price),
                "line_total": money_round(it.line_total),
            }
        )

    return {
        "item_name": item_name,
        "min_price": min_price,
        "max_price": max_price,
        "latest_price": latest_price,
        "percent_change": percent_change,
        "trend": trend,
        "history": history,
    }


def get_all_items_price_summary() -> List[Dict[str, Any]]:
    """Generate price summary for all purchased items."""
    items_qs = BillItem.objects.filter(
        bill__is_deleted=False,
        bill__bill_type=Bill.BillType.PURCHASE,
    ).order_by("bill__bill_date", "bill__id", "id")

    grouped_items: Dict[str, List[Decimal]] = defaultdict(list)
    for it in items_qs:
        name = it.item_name.strip()
        grouped_items[name].append(it.unit_price)

    summary_list = []
    for name, prices in grouped_items.items():
        min_price = money_round(min(prices))
        max_price = money_round(max(prices))
        first_price = prices[0]
        latest_price = money_round(prices[-1])

        if first_price > Decimal("0.00"):
            percent_change = money_round(
                ((latest_price - first_price) / first_price) * Decimal("100")
            )
        else:
            percent_change = Decimal("0.00")

        if latest_price > first_price:
            trend = "increased"
        elif latest_price < first_price:
            trend = "decreased"
        else:
            trend = "stable"

        summary_list.append(
            {
                "name": name,
                "purchase_count": len(prices),
                "latest_price": latest_price,
                "min_price": min_price,
                "max_price": max_price,
                "trend": trend,
                "percent_change": percent_change,
            }
        )

    summary_list.sort(key=lambda x: (-x["purchase_count"], x["name"].lower()))
    return summary_list


def generate_spending_csv(start_date=None, end_date=None) -> str:
    """Export purchase bills to RFC-compliant CSV string."""
    bills = (
        Bill.objects.filter(is_deleted=False, bill_type=Bill.BillType.PURCHASE)
        .select_related("party", "category")
        .order_by("-bill_date", "-id")
    )
    if start_date:
        bills = bills.filter(bill_date__gte=start_date)
    if end_date:
        bills = bills.filter(bill_date__lte=end_date)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(
        [
            "Invoice No",
            "Date",
            "Vendor",
            "Category",
            "Subtotal",
            "Discount",
            "Tax",
            "Grand Total",
            "Amount Paid",
            "Status",
        ]
    )

    for bill in bills:
        writer.writerow(
            [
                bill.invoice_no or f"BILL-{bill.pk}",
                bill.bill_date.strftime("%Y-%m-%d"),
                bill.party.name if bill.party else "",
                bill.category.name if bill.category else "",
                str(bill.subtotal),
                str(bill.discount),
                str(bill.tax),
                str(bill.grand_total),
                str(bill.amount_paid),
                bill.get_payment_status_display(),
            ]
        )

    return output.getvalue()
