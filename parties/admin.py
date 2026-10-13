"""parties/admin.py
=================
Django admin configuration for Party model.
"""

from django.contrib import admin

from parties.models import Party


@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    list_display = ("name", "urdu_name", "party_type", "phone", "email", "is_active", "created_at")
    list_filter = ("party_type", "is_active")
    search_fields = ("name", "urdu_name", "phone", "email", "tax_number")
    ordering = ("name",)
