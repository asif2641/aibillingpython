"""
accounts/views.py
=================
Authentication views for the accounts app.

Provides LoginView with 5-attempt failed login lockout enforcement and
LogoutView redirecting to login.

Business logic resides in accounts/services.py — views stay thin.
"""

from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

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
    """Decorator requiring an authenticated user with Super Admin privileges."""

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
