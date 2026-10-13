"""scanning/admin.py
================
Admin configuration for scanning models.
"""

from django.contrib import admin

from scanning.models import BillEditHistory, BillError, BillFile, ScanJob


@admin.register(BillFile)
class BillFileAdmin(admin.ModelAdmin):
    list_display = ["id", "bill", "page_number", "file_type", "file_size", "created_at"]
    list_filter = ["file_type", "created_at"]
    search_fields = ["file_hash", "bill__invoice_no"]


@admin.register(ScanJob)
class ScanJobAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "status",
        "provider",
        "model_name",
        "token_count",
        "latency_ms",
        "created_at",
    ]
    list_filter = ["status", "provider", "created_at"]
    search_fields = ["bill__invoice_no", "error_message"]


@admin.register(BillError)
class BillErrorAdmin(admin.ModelAdmin):
    list_display = ["id", "bill", "error_type", "severity", "is_resolved", "created_at"]
    list_filter = ["error_type", "severity", "is_resolved"]
    search_fields = ["message", "bill__invoice_no"]


@admin.register(BillEditHistory)
class BillEditHistoryAdmin(admin.ModelAdmin):
    list_display = ["id", "bill", "user", "field_name", "timestamp"]
    search_fields = ["field_name", "bill__invoice_no", "user__username"]
