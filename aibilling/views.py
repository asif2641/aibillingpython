"""aibilling/views.py
==================
Project-level views for the aibilling application.
"""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
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


def service_worker_view(request):
    """Serve the root service worker script with Service-Worker-Allowed header."""
    sw_path = settings.BASE_DIR / "static" / "sw.js"
    if not sw_path.exists():
        raise Http404("Service Worker not found")
    content = sw_path.read_text(encoding="utf-8")
    response = HttpResponse(content, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


def manifest_view(request):
    """Serve the web app manifest."""
    manifest_path = settings.BASE_DIR / "static" / "manifest.json"
    if not manifest_path.exists():
        raise Http404("Manifest not found")
    content = manifest_path.read_text(encoding="utf-8")
    return HttpResponse(content, content_type="application/manifest+json")


def offline_view(request):
    """Render the offline fallback shell."""
    return render(request, "offline.html", {"title": "Offline Mode"})
