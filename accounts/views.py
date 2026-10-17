"""
accounts/views.py
=================
Authentication views for the accounts app.

Provides LoginView with 5-attempt failed login lockout enforcement and
LogoutView redirecting to login.

Business logic resides in accounts/services.py — views stay thin.
"""

from __future__ import annotations

from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from bills.models import Bill

from .forms import (
    CustomAuthenticationForm,
    StaffCreationForm,
    StaffPasswordResetForm,
    UserRegistrationForm,
)
from .services import (
    create_staff_user,
    register_owner_user,
    reset_staff_password,
    toggle_staff_status,
    update_staff_permissions,
)


def register_view(request):
    """Handle self-service registration for new business owners."""
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = register_owner_user(
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
                business_name=form.cleaned_data["business_name"],
                email=form.cleaned_data.get("email", ""),
            )
            login(request, user)
            messages.success(
                request,
                _("Welcome to ScanBooks! Your account is ready with 10 free scans."),
            )
            return redirect("dashboard")
    else:
        form = UserRegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


class LoginView(auth_views.LoginView):
    """Custom login view with 5-attempt account lockout.

    Uses CustomAuthenticationForm which interfaces with accounts.services
    to record failed attempts, lock accounts after 5 failures, and auto-unlock
    after 15 minutes.
    """

    form_class = CustomAuthenticationForm
    authentication_form = CustomAuthenticationForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True
    next_page = reverse_lazy("dashboard")


class LogoutView(auth_views.LogoutView):
    """Custom logout view.

    Terminates the user session and redirects to the login page.
    """

    next_page = reverse_lazy("accounts:login")


def superadmin_required(view_func):
    """Decorator requiring an authenticated user with Super Admin (is_superuser) privileges."""

    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        if not user.is_superuser:
            return HttpResponseForbidden("You do not have permission to access this resource.")
        return view_func(request, *args, **kwargs)

    return _wrapped_view


@superadmin_required
def staff_list_view(request):
    """Display roster of staff accounts with pagination."""
    User = get_user_model()
    users_qs = User.objects.all().order_by("username")
    paginator = Paginator(users_qs, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(
        request,
        "accounts/staff_list.html",
        {
            "page_obj": page_obj,
            "staff_users": page_obj.object_list,
        },
    )


@superadmin_required
def staff_add_view(request):
    """Create a new staff user with role='staff' and granular permissions."""
    if request.method == "POST":
        form = StaffCreationForm(request.POST)
        if form.is_valid():
            create_staff_user(
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
                email=form.cleaned_data.get("email", ""),
                first_name=form.cleaned_data.get("first_name", ""),
                last_name=form.cleaned_data.get("last_name", ""),
                can_delete_records=form.cleaned_data.get("can_delete_records", False),
                can_manage_shop=form.cleaned_data.get("can_manage_shop", False),
                can_manage_categories=form.cleaned_data.get("can_manage_categories", False),
            )
            messages.success(request, _("Staff user created successfully."))
            return redirect("staff_list")
        return render(request, "accounts/staff_form.html", {"form": form}, status=400)

    form = StaffCreationForm()
    return render(request, "accounts/staff_form.html", {"form": form})


@superadmin_required
def staff_toggle_status_view(request, user_id: int):
    """Toggle is_active on target staff user. Cannot disable self."""
    User = get_user_model()
    target_user = get_object_or_404(User, pk=user_id)

    if target_user.pk == request.user.pk:
        messages.error(request, _("You cannot deactivate your own account."))
        return HttpResponseBadRequest("Cannot deactivate your own account.")

    toggle_staff_status(target_user, request.user)
    action_text = _("activated") if target_user.is_active else _("deactivated")
    messages.success(request, _(f"User {target_user.username} has been {action_text}."))
    return redirect("staff_list")


@superadmin_required
def staff_permissions_view(request, user_id: int):
    """Update granular permission flags for a staff account."""
    User = get_user_model()
    target_user = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        can_delete = request.POST.get("can_delete_records") in ["on", "true", "True", "1", True]
        can_shop = request.POST.get("can_manage_shop") in ["on", "true", "True", "1", True]
        can_categories = request.POST.get("can_manage_categories") in [
            "on",
            "true",
            "True",
            "1",
            True,
        ]

        update_staff_permissions(
            target_user=target_user,
            can_delete_records=can_delete,
            can_manage_shop=can_shop,
            can_manage_categories=can_categories,
        )
        messages.success(request, _("Permissions updated successfully."))
        return redirect("staff_list")

    return render(
        request,
        "accounts/staff_permissions.html",
        {"target_user": target_user},
    )


@superadmin_required
def staff_reset_password_view(request, user_id: int):
    """Reset staff user password, clear lockout flags and reset failed attempts."""
    User = get_user_model()
    target_user = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        form = StaffPasswordResetForm(request.POST)
        if form.is_valid():
            reset_staff_password(target_user, form.cleaned_data["new_password"])
            messages.success(request, _(f"Password for {target_user.username} reset successfully."))
            return redirect("staff_list")
        return render(
            request,
            "accounts/staff_reset_password.html",
            {"form": form, "target_user": target_user},
            status=400,
        )

    form = StaffPasswordResetForm()
    return render(
        request,
        "accounts/staff_reset_password.html",
        {"form": form, "target_user": target_user},
    )


@login_required
def subscription_view(request):
    """View and manage SaaS subscription plan and scan quota."""
    user = request.user
    from settings_app.models import LandingPageSettings

    site_settings = LandingPageSettings.get_solo()

    if request.method == "POST":
        action = request.POST.get("action", "")
        plan_selected = request.POST.get("plan", "")

        # Immediate downgrade to free trial
        if action == "downgrade_free" or plan_selected == user.Plan.FREE:
            user.plan = user.Plan.FREE
            user.monthly_scan_quota = getattr(site_settings, "starter_scans", 10) or 10
            user.save(update_fields=["plan", "monthly_scan_quota"])
            messages.success(
                request,
                _("Your subscription has been switched to Free Trial (%(quota)d scans/month).")
                % {"quota": user.monthly_scan_quota},
            )
            return redirect("accounts:subscription")

        # Upgrade Payment submission
        from .forms import SubscriptionPaymentSubmissionForm

        form = SubscriptionPaymentSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            req_obj = form.save(commit=False)
            req_obj.user = user
            req_obj.status = req_obj.Status.PENDING
            req_obj.save()
            messages.success(
                request,
                _(
                    "Payment proof submitted for %(plan)s! Our team will review and activate your quota shortly. You can also send the receipt directly on WhatsApp for instant activation."
                )
                % {"plan": req_obj.get_plan_display()},
            )
            return redirect("accounts:subscription")
        messages.error(request, _("Please provide payment details or valid transaction reference."))

    from .forms import SubscriptionPaymentSubmissionForm
    from .models import SubscriptionPaymentRequest

    pending_request = (
        SubscriptionPaymentRequest.objects.filter(
            user=user, status=SubscriptionPaymentRequest.Status.PENDING
        )
        .order_by("-created_at")
        .first()
    )

    usage_percent = 0
    if user.monthly_scan_quota > 0:
        usage_percent = min(100, int((user.scans_used_this_month / user.monthly_scan_quota) * 100))

    context = {
        "title": _("Subscription & Plan"),
        "user": user,
        "usage_percent": usage_percent,
        "remaining_scans": user.remaining_scans,
        "site_settings": site_settings,
        "pending_request": pending_request,
        "payment_form": SubscriptionPaymentSubmissionForm(),
    }
    return render(request, "accounts/subscription.html", context)


@superadmin_required
def superadmin_dashboard_view(request):
    """Dedicated Frontend Super Admin SaaS Management Dashboard.

    Provides high-level platform KPIs (MRR, tenant count, scan volume, bills)
    and granular tenant administration (tier changes, quota management, account status).
    """
    User = get_user_model()
    tenants_base = User.objects.exclude(is_superuser=True)

    total_tenants = tenants_base.count()
    pro_count = tenants_base.filter(plan=User.Plan.PRO).count()
    business_count = tenants_base.filter(plan=User.Plan.BUSINESS).count()
    free_count = tenants_base.filter(plan=User.Plan.FREE).count()

    pro_price = Decimal("1500.00")
    business_price = Decimal("4000.00")
    estimated_mrr = (Decimal(pro_count) * pro_price) + (Decimal(business_count) * business_price)

    total_scans_used = tenants_base.aggregate(total=Sum("scans_used_this_month"))["total"] or 0

    total_platform_bills = Bill.objects.active().count()
    total_platform_volume = Bill.objects.active().aggregate(total=Sum("grand_total"))[
        "total"
    ] or Decimal("0.00")

    # Filter & Search
    q = request.GET.get("q", "").strip()
    selected_plan = request.GET.get("plan", "").strip().lower()

    tenants_qs = tenants_base.annotate(
        bills_count=Count("created_bills", filter=Q(created_bills__is_deleted=False), distinct=True)
    ).order_by("-date_joined")

    if q:
        tenants_qs = tenants_qs.filter(
            Q(business_name__icontains=q) | Q(username__icontains=q) | Q(email__icontains=q)
        )
    if selected_plan in (User.Plan.FREE, User.Plan.PRO, User.Plan.BUSINESS):
        tenants_qs = tenants_qs.filter(plan=selected_plan)

    paginator = Paginator(tenants_qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    from .models import SubscriptionPaymentRequest

    pending_payment_requests = (
        SubscriptionPaymentRequest.objects.filter(status=SubscriptionPaymentRequest.Status.PENDING)
        .select_related("user")
        .order_by("-created_at")
    )
    pending_payments_count = pending_payment_requests.count()

    context = {
        "title": _("SaaS Super Admin Console"),
        "total_tenants": total_tenants,
        "pro_count": pro_count,
        "business_count": business_count,
        "free_count": free_count,
        "estimated_mrr": estimated_mrr,
        "total_scans_used": total_scans_used,
        "total_platform_bills": total_platform_bills,
        "total_platform_volume": total_platform_volume,
        "page_obj": page_obj,
        "tenants": page_obj.object_list,
        "q": q,
        "selected_plan": selected_plan,
        "plan_choices": User.Plan.choices,
        "pending_payment_requests": pending_payment_requests,
        "pending_payments_count": pending_payments_count,
    }
    return render(request, "accounts/superadmin_dashboard.html", context)


@superadmin_required
def superadmin_create_tenant_view(request):
    """Allow superadmin to provision a new tenant directly from the SaaS console."""
    if request.method != "POST":
        return redirect("accounts:superadmin_dashboard")

    User = get_user_model()
    business_name = request.POST.get("business_name", "").strip()
    username = request.POST.get("username", "").strip()
    email = request.POST.get("email", "").strip()
    password = request.POST.get("password", "")
    plan = request.POST.get("plan", User.Plan.FREE).strip().lower()
    quota_raw = request.POST.get("monthly_scan_quota")

    if not username:
        messages.error(request, _("Username is required."))
        return redirect("accounts:superadmin_dashboard")

    if not password:
        messages.error(request, _("Password is required."))
        return redirect("accounts:superadmin_dashboard")

    if User.objects.filter(username=username).exists():
        messages.error(
            request,
            _("A user with username '%(username)s' already exists.") % {"username": username},
        )
        return redirect("accounts:superadmin_dashboard")

    monthly_quota = int(quota_raw) if (quota_raw and str(quota_raw).isdigit()) else None

    tenant = register_owner_user(
        username=username,
        password=password,
        business_name=business_name or username,
        email=email,
        plan=plan,
        monthly_scan_quota=monthly_quota,
    )
    messages.success(
        request,
        _("New tenant '%(username)s' created successfully (%(plan)s tier, %(quota)d scans/month).")
        % {
            "username": tenant.username,
            "plan": tenant.get_plan_display(),
            "quota": tenant.monthly_scan_quota,
        },
    )
    return redirect("accounts:superadmin_dashboard")


@superadmin_required
def superadmin_update_tenant_plan_view(request, user_id: int):
    """Update tenant subscription tier and monthly scan quota."""
    if request.method != "POST":
        return redirect("accounts:superadmin_dashboard")

    User = get_user_model()
    tenant = get_object_or_404(User, pk=user_id)

    new_plan = request.POST.get("plan")
    new_quota = request.POST.get("monthly_scan_quota")

    if new_plan in (User.Plan.FREE, User.Plan.PRO, User.Plan.BUSINESS):
        tenant.plan = new_plan

    if new_quota is not None and str(new_quota).isdigit():
        tenant.monthly_scan_quota = int(new_quota)
    elif new_plan == User.Plan.FREE:
        tenant.monthly_scan_quota = 10
    elif new_plan == User.Plan.PRO:
        tenant.monthly_scan_quota = 100
    elif new_plan == User.Plan.BUSINESS:
        tenant.monthly_scan_quota = 500

    tenant.save(update_fields=["plan", "monthly_scan_quota"])
    messages.success(
        request,
        _("Subscription plan for %(username)s updated to %(plan)s (%(quota)d scans/month).")
        % {
            "username": tenant.username,
            "plan": tenant.get_plan_display(),
            "quota": tenant.monthly_scan_quota,
        },
    )
    return redirect(request.META.get("HTTP_REFERER") or "accounts:superadmin_dashboard")


@superadmin_required
def superadmin_toggle_tenant_status_view(request, user_id: int):
    """Toggle tenant active status (activate or suspend account)."""
    if request.method != "POST":
        return redirect("accounts:superadmin_dashboard")

    User = get_user_model()
    tenant = get_object_or_404(User, pk=user_id)

    if tenant.pk == request.user.pk:
        messages.error(request, _("You cannot suspend your own superadmin account."))
        return redirect("accounts:superadmin_dashboard")

    tenant.is_active = not tenant.is_active
    tenant.save(update_fields=["is_active"])

    status_label = _("activated") if tenant.is_active else _("suspended")
    messages.success(
        request,
        _("Tenant account %(username)s has been %(status)s.")
        % {"username": tenant.username, "status": status_label},
    )
    return redirect(request.META.get("HTTP_REFERER") or "accounts:superadmin_dashboard")


@superadmin_required
def superadmin_add_bonus_scans_view(request, user_id: int):
    """Add bonus scans to tenant's current monthly scan quota."""
    if request.method != "POST":
        return redirect("accounts:superadmin_dashboard")

    User = get_user_model()
    tenant = get_object_or_404(User, pk=user_id)

    bonus_raw = request.POST.get("bonus_scans", 0)
    try:
        bonus = int(bonus_raw)
        if bonus > 0:
            tenant.monthly_scan_quota += bonus
            tenant.save(update_fields=["monthly_scan_quota"])
            messages.success(
                request,
                _("Granted %(bonus)d bonus scans to %(username)s. New monthly quota: %(total)d.")
                % {
                    "bonus": bonus,
                    "username": tenant.username,
                    "total": tenant.monthly_scan_quota,
                },
            )
        else:
            messages.warning(request, _("Bonus scans must be greater than zero."))
    except (ValueError, TypeError):
        messages.error(request, _("Invalid bonus scan value entered."))

    return redirect(request.META.get("HTTP_REFERER") or "accounts:superadmin_dashboard")


@superadmin_required
def superadmin_approve_payment_request_view(request, request_id: int):
    """Approve tenant payment request and activate their subscription plan and quota."""
    if request.method != "POST":
        return redirect("accounts:superadmin_dashboard")

    from django.utils import timezone

    from settings_app.models import LandingPageSettings

    from .models import SubscriptionPaymentRequest

    payment_req = get_object_or_404(SubscriptionPaymentRequest, pk=request_id)
    site_settings = LandingPageSettings.get_solo()
    tenant = payment_req.user

    tenant.plan = payment_req.plan
    if payment_req.plan == tenant.Plan.PRO:
        tenant.monthly_scan_quota = getattr(site_settings, "pro_scans", 100) or 100
    elif payment_req.plan == tenant.Plan.BUSINESS:
        tenant.monthly_scan_quota = getattr(site_settings, "business_scans", 500) or 500
    tenant.save(update_fields=["plan", "monthly_scan_quota"])

    payment_req.status = SubscriptionPaymentRequest.Status.APPROVED
    payment_req.reviewed_by = request.user
    payment_req.reviewed_at = timezone.now()
    payment_req.save(update_fields=["status", "reviewed_by", "reviewed_at"])

    messages.success(
        request,
        _(
            "Payment approved! Tenant %(username)s is now active on %(plan)s (%(quota)d scans/month)."
        )
        % {
            "username": tenant.username,
            "plan": tenant.get_plan_display(),
            "quota": tenant.monthly_scan_quota,
        },
    )
    return redirect("accounts:superadmin_dashboard")


@superadmin_required
def superadmin_reject_payment_request_view(request, request_id: int):
    """Reject tenant payment request with reason."""
    if request.method != "POST":
        return redirect("accounts:superadmin_dashboard")

    from django.utils import timezone

    from .models import SubscriptionPaymentRequest

    payment_req = get_object_or_404(SubscriptionPaymentRequest, pk=request_id)
    notes = request.POST.get("admin_notes", "").strip()

    payment_req.status = SubscriptionPaymentRequest.Status.REJECTED
    payment_req.admin_notes = notes
    payment_req.reviewed_by = request.user
    payment_req.reviewed_at = timezone.now()
    payment_req.save(update_fields=["status", "admin_notes", "reviewed_by", "reviewed_at"])

    messages.warning(
        request,
        _("Payment request for %(username)s rejected.") % {"username": payment_req.user.username},
    )
    return redirect("accounts:superadmin_dashboard")
