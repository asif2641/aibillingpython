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


class LandingPageSettingsForm(forms.ModelForm):
    """Form for editing public landing page marketing content, video, and contact details."""

    class Meta:
        from .models import LandingPageSettings

        model = LandingPageSettings
        fields = [
            "site_title",
            "hero_badge_en",
            "hero_badge_ur",
            "hero_title_en",
            "hero_title_ur",
            "hero_subtitle_en",
            "hero_subtitle_ur",
            "hero_cta_text_en",
            "hero_cta_text_ur",
            "free_scans_badge_count",
            "demo_video_url",
            "video_button_text_en",
            "video_button_text_ur",
            "support_phone",
            "support_email",
            "whatsapp_number",
            "contact_address",
            "contact_hours",
            "starter_price_pkr",
            "starter_price_usd",
            "starter_scans",
            "pro_price_pkr",
            "pro_price_usd",
            "pro_scans",
            "business_price_pkr",
            "business_price_usd",
            "business_scans",
            "facebook_url",
            "twitter_url",
            "linkedin_url",
            "instagram_url",
            "youtube_url",
            "footer_text_en",
            "footer_text_ur",
            "bank_name",
            "bank_account_title",
            "bank_account_number",
            "bank_iban",
            "jazzcash_number",
            "easypaisa_number",
            "payment_instructions_note",
        ]
        widgets = {
            "hero_subtitle_en": forms.Textarea(attrs={"rows": 2}),
            "hero_subtitle_ur": forms.Textarea(attrs={"rows": 2}),
            "payment_instructions_note": forms.Textarea(attrs={"rows": 2}),
        }
