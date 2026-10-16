"""aibilling/views.py
==================
Project-level views for the aibilling application: dashboard, global search, and PWA endpoints.
"""

from decimal import Decimal

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import connection
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from bills.models import Bill, BillItem
from parties.models import Party
from reports.services import (
    get_spending_by_category,
    get_spending_over_time,
    get_spending_summary,
)
from settings_app.models import ActivityLog
from settings_app.signals import DASHBOARD_CACHE_KEY


@require_GET
def healthcheck_view(request):
    """Verify application and database health for uptime monitors and cloud platforms."""
    import os
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({
            "status": "ok",
            "database": "connected",
            "vendor": connection.vendor,
            "media_root": str(settings.MEDIA_ROOT),
            "commit": os.environ.get("VERCEL_GIT_COMMIT_SHA", "dev")[:7],
        }, status=200)
    except Exception:
        return JsonResponse({"status": "error", "database": "disconnected"}, status=503)


@login_required
def dashboard_view(request):
    """Render the main dashboard layout shell with live financial KPIs.

    Uses Django's cache framework for dashboard aggregations and invalidates
    automatically via signals when Bill or Payment records change.
    """
    cached_data = cache.get(DASHBOARD_CACHE_KEY)
    if cached_data is None:
        summary = get_spending_summary(date_range_key="all")
        chart_data = get_spending_over_time()
        category_breakdown = get_spending_by_category()
        cached_data = {
            "summary": summary,
            "chart_data": chart_data,
            "category_breakdown": category_breakdown,
        }
        cache.set(DASHBOARD_CACHE_KEY, cached_data, timeout=300)
    else:
        summary = cached_data["summary"]
        chart_data = cached_data["chart_data"]
        category_breakdown = cached_data["category_breakdown"]

    recent_bills = (
        Bill.objects.filter(is_deleted=False)
        .select_related("party", "category")
        .prefetch_related("scan_jobs")
        .order_by("-created_at")[:5]
    )
    recent_activities = ActivityLog.objects.select_related("user").order_by("-created_at")[:6]

    context = {
        "title": "Dashboard",
        "total_spend": f"{summary['total_spend']:,.2f}",
        "total_bills": summary["purchase_bills_count"],
        "outstanding_credit": f"{summary['outstanding_credit']:,.2f}",
        "average_bill": f"{summary['average_bill']:,.2f}",
        "top_vendor": summary.get("top_vendor", ""),
        "pending_count": summary.get("pending_count", 0),
        "pending_amount": f"{summary.get('pending_amount', Decimal('0.00')):,.2f}",
        "chart_data": chart_data,
        "category_breakdown": category_breakdown,
        "recent_bills": recent_bills,
        "recent_activities": recent_activities,
    }
    return render(request, "dashboard/index.html", context)


@login_required
def global_search_view(request):
    """Search across bills, parties, and bill line items (English and Urdu)."""
    q = request.GET.get("q", "").strip()
    if q:
        bills = list(
            Bill.objects.filter(is_deleted=False)
            .select_related("party", "category")
            .filter(
                Q(invoice_no__icontains=q)
                | Q(notes__icontains=q)
                | Q(party__name__icontains=q)
                | Q(party__urdu_name__icontains=q)
            )
            .distinct()[:20]
        )
        parties = list(
            Party.objects.filter(is_active=True)
            .filter(Q(name__icontains=q) | Q(urdu_name__icontains=q) | Q(phone__icontains=q))
            .distinct()[:20]
        )
        items = list(
            BillItem.objects.filter(bill__is_deleted=False)
            .select_related("bill", "bill__party")
            .filter(Q(item_name__icontains=q) | Q(urdu_item_name__icontains=q))
            .distinct()[:20]
        )
    else:
        bills = []
        parties = []
        items = []

    return render(
        request,
        "search_results.html",
        {
            "query": q,
            "bills": bills,
            "parties": parties,
            "items": items,
            "total_results": len(bills) + len(parties) + len(items),
        },
    )


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
