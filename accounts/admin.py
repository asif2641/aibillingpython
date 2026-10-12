"""
accounts/admin.py
==================
Django admin configuration for the User model.

Extends UserAdmin so we keep all built-in user management features
(password change form, permission groups, etc.) and add our custom fields.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """Admin panel for the custom User model.

    Adds role, lock status, and security fields to the built-in UserAdmin.
    """

    # Columns shown in the user list view.
    list_display = [
        "username",
        "email",
        "role",
        "is_active",
        "is_locked",
        "failed_login_attempts",
        "date_joined",
    ]

    # Filters in the right sidebar of the list view.
    list_filter = ["role", "is_active", "is_locked", "is_staff"]

    # Fields that can be searched in the search bar.
    search_fields = ["username", "email", "first_name", "last_name"]

    # Add our custom fields to the existing UserAdmin fieldsets.
    fieldsets = UserAdmin.fieldsets + (  # type: ignore[operator]
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
            _("Role & Security"),
            {
                "fields": ("role",),
            },
        ),
    )
