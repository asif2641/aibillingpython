"""
settings_app/views.py
=====================
Views for the settings_app application: shop profile, activity audit logs, and backups/exports.
"""

from __future__ import annotations

import json
import shutil
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from bills.models import Bill, BillItem
from categories.models import Category, Unit
from ledger.models import Payment
from parties.models import Party
from scanning.models import BillEditHistory, BillError, BillFile, ScanJob
from sync.models import SyncQueue

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


def superadmin_required(view_func):
    """Decorator requiring login and Super Admin permissions."""

    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        is_super = (
            user.is_superuser
            or getattr(user, "is_superadmin", False)
            or getattr(user, "role", "") == "superadmin"
        )
        if not is_super:
            return HttpResponseForbidden("Only super admins are allowed to access this page.")
        return view_func(request, *args, **kwargs)

    return _wrapped_view


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


def _get_reset_summary_context(request) -> dict:
    """Collect record counts for reset confirmation screen."""
    return {
        "active_tab": "reset",
        "bills_count": Bill.all_objects.count(),
        "parties_count": Party.objects.count(),
        "payments_count": Payment.objects.count(),
        "scans_count": ScanJob.objects.count(),
        "files_count": BillFile.objects.count(),
        "logs_count": ActivityLog.objects.count(),
        "categories_count": Category.objects.count(),
        "units_count": Unit.objects.count(),
        "staff_count": User.objects.exclude(pk=request.user.pk).count(),
    }


@superadmin_required
def reset_data_view(request):
    """Factory reset all application data for a new client installation.

    Strictly limited to Super Admins. Requires typing 'RESET' to confirm.
    Wipes bills, payments, parties, scans, uploaded media files, sync queue,
    activity logs, restores default categories/units, resets shop profile,
    and optionally removes non-superadmin staff.
    """
    if request.method == "POST":
        confirm_code = request.POST.get("confirm_code", "").strip()
        if confirm_code != "RESET":
            messages.error(
                request,
                _(
                    "Confirmation code did not match. You must type RESET in capital letters to confirm."
                ),
            )
            context = _get_reset_summary_context(request)
            return render(request, "settings_app/reset_data.html", context, status=400)

        reset_staff = request.POST.get("reset_staff") == "on"

        with transaction.atomic():
            # 1. Delete payments (safe before parties or bills)
            Payment.objects.all().delete()

            # 2. Delete scanning records and uploaded file references
            BillError.objects.all().delete()
            BillEditHistory.objects.all().delete()
            BillFile.objects.all().delete()
            ScanJob.objects.all().delete()

            # 3. Delete bills and items (including trashed bills)
            BillItem.objects.all().delete()
            Bill.all_objects.all().delete()

            # 4. Delete offline sync items
            SyncQueue.objects.all().delete()

            # 5. Delete parties/vendors/customers
            Party.objects.all().delete()

            # 6. Reset categories and units to factory seed defaults
            Category.objects.all().delete()
            Category.seed_defaults()
            Unit.objects.all().delete()
            Unit.seed_defaults()

            # 7. Reset ShopProfile singleton to factory default
            profile = ShopProfile.get_solo()
            profile.name = "My Shop"
            profile.logo = None
            profile.address = ""
            profile.phone = ""
            profile.email = ""
            profile.tax_number = ""
            profile.currency = "PKR"
            profile.timezone = "Asia/Karachi"
            profile.date_format = "YYYY-MM-DD"
            profile.default_language = "en"
            profile.invoice_footer_text = ""
            profile.daily_scan_limit = 50
            profile.monthly_scan_limit = 500
            profile.save()

            # 8. Optionally delete non-superadmin staff accounts (preserving active superadmin)
            if reset_staff:
                User.objects.exclude(pk=request.user.pk).delete()

            # 9. Clean physical uploaded media files from disk
            bills_media_dir = Path(settings.MEDIA_ROOT) / "bills"
            if bills_media_dir.exists():
                shutil.rmtree(bills_media_dir, ignore_errors=True)
                bills_media_dir.mkdir(parents=True, exist_ok=True)

            shop_media_dir = Path(settings.MEDIA_ROOT) / "shop"
            if shop_media_dir.exists():
                shutil.rmtree(shop_media_dir, ignore_errors=True)
                shop_media_dir.mkdir(parents=True, exist_ok=True)

            # 10. Clear past activity logs and log fresh reset action
            ActivityLog.objects.all().delete()
            log_activity(
                user=request.user,
                action="system_reset",
                target_type="System",
                description="System factory reset completed by superadmin for new client installation.",
                ip_address=_get_client_ip(request),
            )

        messages.success(
            request,
            _(
                "All application data has been permanently reset. The system is ready for a new client."
            ),
        )
        return redirect("shop_profile")

    context = _get_reset_summary_context(request)
    return render(request, "settings_app/reset_data.html", context)
