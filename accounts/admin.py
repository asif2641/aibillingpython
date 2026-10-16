"""
accounts/admin.py
=================
Django admin configuration for the custom User model.

Extends UserAdmin so we keep all built-in user management features
(password change form, permission groups, etc.) and add our custom fields.
Only superadmins can manage user accounts. Staff members without superadmin
privileges are restricted.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """Admin panel for the custom User model.

    Adds role, lock status, security fields, and unlocking actions.
    Enforces that only superadmins can view and edit user accounts.
    """

    # Columns shown in the user list view.
    list_display = [
        "username",
        "email",
        "business_name",
        "plan",
        "monthly_scan_quota",
        "scans_used_this_month",
        "role",
        "is_active",
        "is_locked",
        "date_joined",
    ]

    # Filters in the right sidebar of the list view.
    list_filter = ["plan", "role", "is_active", "is_locked", "is_staff"]

    # Fields that can be searched in the search bar.
    search_fields = ["username", "email", "business_name", "first_name", "last_name"]

    # Bulk actions in the admin list view.
    actions = ["unlock_accounts", "lock_accounts"]

    # Add our custom fields to the existing UserAdmin fieldsets.
    fieldsets = UserAdmin.fieldsets + (  # type: ignore[operator]
        (
            _("SaaS Plan & Quota"),
            {
                "fields": (
                    "business_name",
                    "plan",
                    "monthly_scan_quota",
                    "scans_used_this_month",
                    "quota_reset_date",
                )
            },
        ),
        (
            _("Role & Security"),
            {
                "fields": (
                    "role",
                    "is_locked",
                    "locked_until",
                    "failed_login_attempts",
                    "last_login_attempt",
                )
            },
        ),
    )

    # Also show custom fields in the "Add User" form.
    add_fieldsets = UserAdmin.add_fieldsets + (  # type: ignore[operator]
        (
            _("SaaS Plan & Role"),
            {
                "fields": ("business_name", "plan", "role", "monthly_scan_quota"),
            },
        ),
    )

    @admin.action(description=_("Unlock selected user accounts"))
    def unlock_accounts(self, request, queryset):
        """Reset lock status and failed attempts for selected users."""
        count = queryset.update(
            is_locked=False,
            locked_until=None,
            failed_login_attempts=0,
        )
        self.message_user(
            request,
            _("Successfully unlocked %(count)d account(s).") % {"count": count},
        )

    @admin.action(description=_("Lock selected user accounts for 15 minutes"))
    def lock_accounts(self, request, queryset):
        """Manually lock selected users for 15 minutes."""
        count = queryset.update(
            is_locked=True,
            locked_until=timezone.now() + timedelta(minutes=15),
        )
        self.message_user(
            request,
            _("Successfully locked %(count)d account(s).") % {"count": count},
        )

    def has_module_permission(self, request):
        """Allow module access to superadmins, or staff with explicit permissions."""
        if not request.user.is_authenticated or not request.user.is_staff:
            return False
        if request.user.is_superuser or request.user.role == User.Role.SUPERADMIN:
            return True
        return super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        """Allow viewing users to superadmins, or staff with explicit permissions."""
        if not request.user.is_authenticated or not request.user.is_staff:
            return False
        if request.user.is_superuser or request.user.role == User.Role.SUPERADMIN:
            return True
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        """Superadmin can edit any user; non-superadmins cannot edit superadmins."""
        if not request.user.is_authenticated or not request.user.is_staff:
            return False
        if request.user.is_superuser or request.user.role == User.Role.SUPERADMIN:
            return True
        if obj is not None and (obj.is_superuser or obj.role == User.Role.SUPERADMIN):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        """Superadmin can delete users; non-superadmins cannot delete superadmins."""
        if not request.user.is_authenticated or not request.user.is_staff:
            return False
        if request.user.is_superuser or request.user.role == User.Role.SUPERADMIN:
            return True
        if obj is not None and (obj.is_superuser or obj.role == User.Role.SUPERADMIN):
            return False
        return super().has_delete_permission(request, obj)

    def has_add_permission(self, request):
        """Allow adding users to superadmins."""
        if not request.user.is_authenticated or not request.user.is_staff:
            return False
        if request.user.is_superuser or request.user.role == User.Role.SUPERADMIN:
            return True
        return super().has_add_permission(request)
