"""ledger/admin.py
================
Admin configuration for Payment model.
"""

from django.contrib import admin

from ledger.models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "party",
        "bill",
        "amount",
        "payment_date",
        "payment_method",
        "is_deleted",
    )
    list_filter = ("payment_method", "payment_date", "is_deleted")
    search_fields = ("reference", "party__name", "notes")
