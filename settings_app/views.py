"""
settings_app/views.py
=====================
Views for the settings_app application: shop profile, activity audit logs, and backups/exports.
"""

from __future__ import annotations

import json
from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from bills.models import Bill
from categories.models import Category
from ledger.models import Payment
from parties.models import Party

from .forms import ShopProfileForm
from .models import ActivityLog, ShopProfile
from .services import (
    create_database_backup,
    generate_all_bills_csv,
    generate_backup_payload,
    list_backup_files,
    log_activity,
)

User = get_user_model()


def _get_client_ip(request) -> str | None:
    """Extract client IP address from request headers."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def shop_management_required(view_func):
    """Decorator requiring login and either superadmin or can_manage_shop permission."""

    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        is_super = (
            user.is_superuser
            or getattr(user, "is_superadmin", False)
            or getattr(user, "role", "") == "superadmin"
        )
        can_manage = getattr(user, "can_manage_shop", False)
        if not (is_super or can_manage):
            return HttpResponseForbidden("You do not have permission to manage shop settings.")
        return view_func(request, *args, **kwargs)

    return _wrapped_view


@shop_management_required
def shop_profile_view(request):
    """View and update shop profile singleton configuration."""
    profile = ShopProfile.get_solo()

    if request.method == "POST":
        form = ShopProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            log_activity(
                user=request.user,
                action="settings_updated",
                target_type="ShopProfile",
                target_id=profile.pk,
                description=f"Updated shop profile settings ({profile.name})",
                ip_address=_get_client_ip(request),
            )
            messages.success(request, _("Shop profile updated successfully."))
            return redirect(request.path)
        return render(
            request,
            "settings_app/shop_profile.html",
            {"form": form, "profile": profile, "active_tab": "shop"},
            status=400,
        )

    form = ShopProfileForm(instance=profile)
    return render(
        request,
        "settings_app/shop_profile.html",
        {"form": form, "profile": profile, "active_tab": "shop"},
    )


@shop_management_required
def activity_log_view(request):
    """Display paginated audit log of system and user actions."""
    qs = ActivityLog.objects.select_related("user").all()

    action_filter = request.GET.get("action", "").strip()
    user_filter = request.GET.get("user", "").strip()
    search_query = request.GET.get("q", "").strip()

    if action_filter:
        qs = qs.filter(action=action_filter)
    if user_filter and user_filter.isdigit():
        qs = qs.filter(user_id=int(user_filter))
    if search_query:
        qs = qs.filter(
            Q(description__icontains=search_query)
            | Q(action__icontains=search_query)
            | Q(target_type__icontains=search_query)
        )

    paginator = Paginator(qs, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    available_actions = (
        ActivityLog.objects.values_list("action", flat=True).distinct().order_by("action")
    )
    users = User.objects.filter(is_active=True).order_by("username")

    return render(
        request,
        "settings_app/activity_log.html",
        {
            "logs": page_obj,
            "page_obj": page_obj,
            "active_tab": "activity_log",
            "action_filter": action_filter,
            "user_filter": user_filter,
            "search_query": search_query,
            "available_actions": available_actions,
            "users": users,
        },
    )


@shop_management_required
def backup_export_view(request):
    """Display database backup management and export options."""
    backups = list_backup_files()
    context = {
        "active_tab": "backups",
        "backups": backups,
        "bills_count": Bill.objects.filter(is_deleted=False).count(),
        "parties_count": Party.objects.filter(is_active=True).count(),
        "payments_count": Payment.objects.filter(is_deleted=False).count(),
        "categories_count": Category.objects.filter(is_archived=False).count(),
    }
    return render(request, "settings_app/backup_export.html", context)


@shop_management_required
def backup_create_view(request):
    """Trigger an immediate server-side JSON backup file creation."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    backup_path = create_database_backup(user=request.user)
    messages.success(
        request,
        _("Database backup created successfully: %(filename)s") % {"filename": backup_path.name},
    )
    return redirect("backup_export")


@shop_management_required
def backup_download_json_view(request):
    """Download a complete non-sensitive JSON backup of shop data."""
    payload = generate_backup_payload()
    date_str = timezone.now().strftime("%Y%m%d")
    filename = f"aibilling_backup_{date_str}.json"

    log_activity(
        user=request.user,
        action="backup_downloaded",
        target_type="System",
        description=f"Downloaded JSON database backup ({filename})",
        ip_address=_get_client_ip(request),
    )

    response = HttpResponse(
        json.dumps(payload, indent=2, ensure_ascii=False),
        content_type="application/json",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@shop_management_required
def backup_download_csv_view(request):
    """Download a comprehensive CSV export of all active bills."""
    csv_content = generate_all_bills_csv()
    date_str = timezone.now().strftime("%Y%m%d")
    filename = f"aibilling_bills_export_{date_str}.csv"

    log_activity(
        user=request.user,
        action="csv_exported",
        target_type="Bill",
        description=f"Downloaded all bills CSV export ({filename})",
        ip_address=_get_client_ip(request),
    )

    response = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
