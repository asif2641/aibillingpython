"""
settings_app/forms.py
=====================
Forms for shop profile and configuration management.
"""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import ShopProfile


class ShopProfileForm(forms.ModelForm):
    """Form for viewing and updating ShopProfile singleton settings."""

    class Meta:
        model = ShopProfile
        fields = [
            "name",
            "logo",
            "address",
            "phone",
            "email",
            "tax_number",
            "currency",
            "timezone",
            "date_format",
            "default_language",
            "invoice_footer_text",
            "daily_scan_limit",
            "monthly_scan_limit",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "invoice_footer_text": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_name(self) -> str:
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError(_("Shop name is required."))
        return name

    def clean_daily_scan_limit(self) -> int:
        limit = self.cleaned_data.get("daily_scan_limit")
        if limit is not None and limit < 0:
            raise forms.ValidationError(_("Daily scan limit cannot be negative."))
        return limit

    def clean_monthly_scan_limit(self) -> int:
        limit = self.cleaned_data.get("monthly_scan_limit")
        if limit is not None and limit < 0:
            raise forms.ValidationError(_("Monthly scan limit cannot be negative."))
        return limit
