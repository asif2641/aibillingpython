"""reports/views.py
================
Views for spending analytics, category breakdowns, price history, and CSV exports.
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from parties.models import Party
from reports.services import (
    generate_incorrect_bills_csv,
    generate_spending_csv,
    get_all_items_price_summary,
    get_date_range,
    get_incorrect_bills_report,
    get_item_price_history,
    get_spending_by_category,
    get_spending_over_time,
    get_spending_summary,
    get_top_vendors,
)


@login_required
def spending_report_view(request: HttpRequest) -> HttpResponse:
    """Render spending analytics, charts, category breakdown, and top vendors."""
    range_key = request.GET.get("range", "all")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    start, end = get_date_range(range_key, start_date, end_date)

    summary = get_spending_summary(
        date_range_key=range_key, custom_start=start_date, custom_end=end_date
    )
    category_breakdown = get_spending_by_category(start_date=start, end_date=end)
    top_vendors = get_top_vendors(limit=10, start_date=start, end_date=end)
    chart_data = get_spending_over_time(interval="day", start_date=start, end_date=end)

    context = {
        "title": "Spending Reports",
        "range_key": range_key,
        "start_date": start_date or "",
        "end_date": end_date or "",
        "summary": summary,
        "category_breakdown": category_breakdown,
        "top_vendors": top_vendors,
        "chart_data": chart_data,
    }
    return render(request, "reports/spending_report.html", context)


@login_required
def export_spending_csv_view(request: HttpRequest) -> HttpResponse:
    """Export filtered purchase spending data as an RFC-compliant CSV."""
    range_key = request.GET.get("range", "all")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    start, end = get_date_range(range_key, start_date, end_date)
    csv_content = generate_spending_csv(start_date=start, end_date=end)

    today_str = timezone.now().date().strftime("%Y-%m-%d")
    response = HttpResponse(csv_content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="spending-report-{today_str}.csv"'
    return response


@login_required
def price_history_view(request: HttpRequest) -> HttpResponse:
    """Render repeat purchase item index and price fluctuation trends."""
    item_query = request.GET.get("item", "").strip()
    items_summary = get_all_items_price_summary()

    item_report = None
    if item_query:
        item_report = get_item_price_history(item_query)

    context = {
        "title": "Price History",
        "items_summary": items_summary,
        "item_report": item_report,
        "selected_item": item_query,
    }
    return render(request, "reports/price_history.html", context)


@login_required
def incorrect_bills_report_view(request: HttpRequest) -> HttpResponse:
    """Render dedicated report of incorrect/discrepant bills with filters and KPIs."""
    range_key = request.GET.get("range", "all")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    party_type = request.GET.get("party_type", "all").strip().lower()
    party_id = request.GET.get("party") or request.GET.get("party_id")
    query = request.GET.get("q", "").strip()
    resolution_status = request.GET.get("resolution", "all").strip().lower()

    start, end = get_date_range(range_key, start_date, end_date)

    report_data = get_incorrect_bills_report(
        start_date=start,
        end_date=end,
        party_type=party_type,
        party_id=party_id,
        query=query,
        resolution_status=resolution_status,
    )

    parties_qs = Party.objects.filter(is_active=True)
    if party_type == "vendor":
        parties_qs = parties_qs.filter(party_type__in=["vendor", "both"])
    elif party_type == "customer":
        parties_qs = parties_qs.filter(party_type__in=["customer", "both"])
    parties = parties_qs.order_by("name")

    selected_party = None
    if party_id:
        selected_party = Party.objects.filter(pk=party_id).first()

    context = {
        "title": "Incorrect & Discrepant Bills Report",
        "range_key": range_key,
        "start_date": start_date or "",
        "end_date": end_date or "",
        "party_type": party_type,
        "party_id": party_id or "",
        "selected_party": selected_party,
        "parties": parties,
        "query": query,
        "resolution_status": resolution_status,
        "report": report_data,
        "records": report_data["records"],
    }
    return render(request, "reports/incorrect_bills.html", context)


@login_required
def export_incorrect_bills_csv_view(request: HttpRequest) -> HttpResponse:
    """Export filtered incorrect bills records as an RFC-compliant CSV."""
    range_key = request.GET.get("range", "all")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    party_type = request.GET.get("party_type", "all").strip().lower()
    party_id = request.GET.get("party") or request.GET.get("party_id")
    query = request.GET.get("q", "").strip()
    resolution_status = request.GET.get("resolution", "all").strip().lower()

    start, end = get_date_range(range_key, start_date, end_date)
    csv_content = generate_incorrect_bills_csv(
        start_date=start,
        end_date=end,
        party_type=party_type,
        party_id=party_id,
        query=query,
        resolution_status=resolution_status,
    )

    today_str = timezone.now().date().strftime("%Y-%m-%d")
    response = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="incorrect-bills-report-{today_str}.csv"'
    )
    return response
