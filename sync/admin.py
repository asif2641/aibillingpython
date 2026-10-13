"""
sync/admin.py
==============
Admin configuration for the sync app.
"""

from django.contrib import admin

from sync.models import SyncQueue


@admin.register(SyncQueue)
class SyncQueueAdmin(admin.ModelAdmin):
    """Admin configuration for SyncQueue model."""

    list_display = (
        "client_id",
        "user",
        "record_type",
        "action",
        "status",
        "retry_count",
        "resolved_record_id",
        "server_timestamp",
        "processed_at",
    )
    list_filter = ("status", "record_type", "action")
    search_fields = ("client_id", "error_message")
    readonly_fields = ("server_timestamp", "processed_at")
