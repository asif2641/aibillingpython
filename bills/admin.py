"""bills/admin.py
===============
Admin configuration for Bill and BillItem models.
"""

from django.contrib import admin

from bills.models import Bill, BillItem


class BillItemInline(admin.TabularInline):
    model = BillItem
    extra = 1


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_no",
        "party",
        "bill_date",
        "bill_type",
        "status",
        "grand_total",
        "payment_status",
        "is_deleted",
    )
    list_filter = ("bill_type", "status", "payment_status", "is_deleted", "bill_date")
    search_fields = ("invoice_no", "party__name", "notes")
    inlines = [BillItemInline]


@admin.register(BillItem)
class BillItemAdmin(admin.ModelAdmin):
    list_display = (
        "bill",
        "serial_no",
        "item_name",
        "quantity",
        "unit",
        "unit_price",
        "line_total",
    )
    search_fields = ("item_name", "urdu_item_name", "bill__invoice_no")
