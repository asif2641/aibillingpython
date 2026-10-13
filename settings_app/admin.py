"""
settings_app/admin.py
================
Admin configuration for the settings_app app.
"""

from django.contrib import admin

from settings_app.models import ActivityLog, ShopProfile


@admin.register(ShopProfile)
class ShopProfileAdmin(admin.ModelAdmin):
    """Admin interface for the ShopProfile singleton."""

    list_display = ("name", "currency", "timezone", "daily_scan_limit", "monthly_scan_limit")


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """Read-oriented admin interface for ActivityLog audit records."""

    list_display = ("action", "user", "target_type", "target_id", "ip_address", "created_at")
    list_filter = ("action", "target_type", "created_at")
    search_fields = ("action", "description", "target_type", "user__username")
    readonly_fields = (
        "user",
        "action",
        "target_type",
        "target_id",
        "description",
        "ip_address",
        "metadata",
        "created_at",
    )
