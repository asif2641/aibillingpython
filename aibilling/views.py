"""aibilling/views.py
==================
Project-level views for the aibilling application.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from reports.services import (
    get_spending_by_category,
    get_spending_over_time,
    get_spending_summary,
)


@login_required
def dashboard_view(request):
    """Render the main dashboard layout shell with live financial KPIs.

    Requires authentication; unauthenticated users are redirected
    to the login page by the @login_required decorator.
    """
    summary = get_spending_summary(date_range_key="all")
    chart_data = get_spending_over_time()
    category_breakdown = get_spending_by_category()

    context = {
        "title": "Dashboard",
        "total_spend": f"{summary['total_spend']:,.2f}",
        "total_bills": summary["purchase_bills_count"],
        "outstanding_credit": f"{summary['outstanding_credit']:,.2f}",
        "average_bill": f"{summary['average_bill']:,.2f}",
        "top_vendor": summary.get("top_vendor", ""),
        "chart_data": chart_data,
        "category_breakdown": category_breakdown,
    }
    return render(request, "dashboard/index.html", context)
