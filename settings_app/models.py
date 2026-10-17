"""
settings_app/models.py
======================
Shop profile and application settings models.

Implements the ShopProfile singleton model holding business identity,
tax, localization, receipt footer, and scanning limit settings.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class ShopProfile(models.Model):
    """Singleton model representing shop-wide configuration and billing identity."""

    name = models.CharField(
        max_length=255,
        default="My Shop",
        verbose_name=_("shop name"),
        help_text=_("Business name displayed on invoices and receipts."),
    )

    logo = models.ImageField(
        upload_to="shop/",
        null=True,
        blank=True,
        verbose_name=_("shop logo"),
        help_text=_("Optional business logo for printed invoices and dashboard."),
    )

    address = models.TextField(
        blank=True,
        default="",
        verbose_name=_("address"),
        help_text=_("Physical address of the shop or business."),
    )

    phone = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name=_("phone"),
        help_text=_("Primary contact phone number."),
    )

    email = models.EmailField(
        blank=True,
        default="",
        verbose_name=_("email"),
        help_text=_("Contact or billing email address."),
    )

    tax_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("tax / NTN number"),
        help_text=_("National Tax Number or Sales Tax Registration Number."),
    )

    currency = models.CharField(
        max_length=10,
        default="PKR",
        verbose_name=_("currency"),
        help_text=_("Standard currency code (e.g. PKR, USD, EUR)."),
    )

    timezone = models.CharField(
        max_length=50,
        default="Asia/Karachi",
        verbose_name=_("timezone"),
        help_text=_("Local timezone for displaying dates and times."),
    )

    date_format = models.CharField(
        max_length=20,
        default="YYYY-MM-DD",
        verbose_name=_("date format"),
        help_text=_("Date presentation format."),
    )

    default_language = models.CharField(
        max_length=5,
        default="en",
        verbose_name=_("default language"),
        help_text=_("Default language code (e.g. en, ur)."),
    )

    invoice_footer_text = models.TextField(
        blank=True,
        default="",
        verbose_name=_("invoice footer text"),
        help_text=_("Custom message or return policy printed at the bottom of bills."),
    )

    daily_scan_limit = models.PositiveIntegerField(
        default=50,
        validators=[MinValueValidator(0)],
        verbose_name=_("daily scan limit"),
        help_text=_("Maximum bill scans allowed per day."),
    )

    monthly_scan_limit = models.PositiveIntegerField(
        default=500,
        validators=[MinValueValidator(0)],
        verbose_name=_("monthly scan limit"),
        help_text=_("Maximum bill scans allowed per month."),
    )

    class Meta:
        verbose_name = _("shop profile")
        verbose_name_plural = _("shop profile")

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        """Validate singleton fields and boundary conditions."""
        super().clean()
        if not self.name or not self.name.strip():
            raise ValidationError({"name": _("Shop name cannot be empty.")})
        if self.daily_scan_limit is not None and self.daily_scan_limit < 0:
            raise ValidationError({"daily_scan_limit": _("Daily scan limit cannot be negative.")})
        if self.monthly_scan_limit is not None and self.monthly_scan_limit < 0:
            raise ValidationError(
                {"monthly_scan_limit": _("Monthly scan limit cannot be negative.")}
            )

    def save(self, *args, **kwargs) -> None:
        """Enforce singleton constraint by ensuring pk=1."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> ShopProfile:
        """Retrieve the existing singleton instance or create the default."""
        try:
            obj, _ = cls.objects.get_or_create(pk=1)
            return obj
        except Exception:
            return cls(pk=1, name="ScanBooks Shop")


class ActivityLog(models.Model):
    """Audit trail record for key financial, party, settings, and system actions."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
        verbose_name=_("user"),
    )
    action = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name=_("action"),
    )
    target_type = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name=_("target type"),
    )
    target_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("target ID"),
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name=_("description"),
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_("IP address"),
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("metadata"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name=_("created at"),
    )

    class Meta:
        verbose_name = _("activity log")
        verbose_name_plural = _("activity logs")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["target_type", "target_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} by {self.user or 'System'} at {self.created_at}"


class LandingPageSettings(models.Model):
    """Singleton model representing public landing page content, video demo, and marketing configuration."""

    # 1. Branding & Identity
    site_title = models.CharField(
        max_length=150,
        default="ScanBooks",
        verbose_name=_("site title / brand"),
        help_text=_("Brand name displayed in the navbar, hero, and footer."),
    )

    # 2. Hero Section
    hero_badge_en = models.CharField(
        max_length=255,
        default="✨ Automated AI Invoicing & Smart Khata",
        verbose_name=_("hero badge (English)"),
    )
    hero_badge_ur = models.CharField(
        max_length=255,
        default="✨ جدید ترین AI کے ذریعے رسیدیں اور کھاتہ خودکار بنائیں",
        verbose_name=_("hero badge (Urdu)"),
    )
    hero_title_en = models.CharField(
        max_length=255,
        default="Turn Paper Bills into Smart Accounts in 5 Seconds",
        verbose_name=_("hero title (English)"),
    )
    hero_title_ur = models.CharField(
        max_length=255,
        default="کاغذی بلوں اور پرچیوں سے نجات۔ صرف 5 سیکنڈ میں خودکار ڈیجیٹل کھاتہ!",
        verbose_name=_("hero title (Urdu)"),
    )
    hero_subtitle_en = models.TextField(
        default="Snap a photo of any handwritten or printed receipt. ScanBooks extracts line items, updates customer ledgers, and generates instant WhatsApp bills without manual typing.",
        verbose_name=_("hero subtitle (English)"),
    )
    hero_subtitle_ur = models.TextField(
        default="موبائل کیمرے سے کسی بھی ہاتھ سے لکھے یا پرنٹ شدہ بل کی تصویر لیں۔ ہمارا AI خودکار اشیاء، ریٹس اور ٹوٹل نکال کر گاہک کا کھاتہ اور واٹس ایپ رپورٹ فوراً تیار کر دیتا ہے۔",
        verbose_name=_("hero subtitle (Urdu)"),
    )
    hero_cta_text_en = models.CharField(
        max_length=100,
        default="Start 10 Free Scans",
        verbose_name=_("hero primary CTA text (English)"),
    )
    hero_cta_text_ur = models.CharField(
        max_length=100,
        default="10 بلز مفت اسکین کریں",
        verbose_name=_("hero primary CTA text (Urdu)"),
    )
    free_scans_badge_count = models.PositiveIntegerField(
        default=10,
        verbose_name=_("free trial scans count"),
        help_text=_("Number of free trial scans highlighted on buttons and badges."),
    )

    # 3. Demo Video Settings
    demo_video_url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name=_("demo video URL"),
        help_text=_(
            "YouTube link, Vimeo link, or MP4 video URL. If left empty, interactive animated demo will be displayed."
        ),
    )
    video_button_text_en = models.CharField(
        max_length=100,
        default="Watch 45s Video Demo",
        verbose_name=_("video button text (English)"),
    )
    video_button_text_ur = models.CharField(
        max_length=100,
        default="45 سیکنڈ کی ویڈیو دیکھیں",
        verbose_name=_("video button text (Urdu)"),
    )

    # 4. Contact & Support Information
    support_phone = models.CharField(
        max_length=50,
        blank=True,
        default="+92 300 1234567",
        verbose_name=_("support phone number"),
        help_text=_("Official phone number displayed for customer assistance."),
    )
    support_email = models.EmailField(
        blank=True,
        default="support@scanbooks.pk",
        verbose_name=_("support email address"),
        help_text=_("Official email address for customer inquiries and help."),
    )
    whatsapp_number = models.CharField(
        max_length=50,
        blank=True,
        default="+923001234567",
        verbose_name=_("WhatsApp number"),
        help_text=_("WhatsApp contact number with country code (e.g. +923001234567)."),
    )
    contact_address = models.CharField(
        max_length=255,
        blank=True,
        default="Lahore, Pakistan",
        verbose_name=_("office address / city"),
    )
    contact_hours = models.CharField(
        max_length=100,
        blank=True,
        default="Mon - Sat: 9:00 AM - 8:00 PM",
        verbose_name=_("support working hours"),
    )

    # 5. Social Media Links
    facebook_url = models.URLField(blank=True, default="", verbose_name=_("Facebook URL"))
    twitter_url = models.URLField(blank=True, default="", verbose_name=_("Twitter / X URL"))
    linkedin_url = models.URLField(blank=True, default="", verbose_name=_("LinkedIn URL"))
    instagram_url = models.URLField(blank=True, default="", verbose_name=_("Instagram URL"))
    youtube_url = models.URLField(blank=True, default="", verbose_name=_("YouTube URL"))

    # 6. Pricing Packages
    starter_price_pkr = models.CharField(
        max_length=50, default="0", verbose_name=_("Starter price (PKR)")
    )
    starter_price_usd = models.CharField(
        max_length=50, default="0", verbose_name=_("Starter price (USD)")
    )
    starter_scans = models.PositiveIntegerField(default=10, verbose_name=_("Starter monthly scans"))

    pro_price_pkr = models.CharField(
        max_length=50, default="1,499", verbose_name=_("Pro price (PKR)")
    )
    pro_price_usd = models.CharField(
        max_length=50, default="9.99", verbose_name=_("Pro price (USD)")
    )
    pro_scans = models.PositiveIntegerField(default=150, verbose_name=_("Pro monthly scans"))

    business_price_pkr = models.CharField(
        max_length=50, default="3,999", verbose_name=_("Business price (PKR)")
    )
    business_price_usd = models.CharField(
        max_length=50, default="24.99", verbose_name=_("Business price (USD)")
    )
    business_scans = models.PositiveIntegerField(
        default=500, verbose_name=_("Business monthly scans")
    )

    # 7. Footer & Legal
    footer_text_en = models.CharField(
        max_length=255,
        default="All rights reserved.",
        verbose_name=_("footer copyright notice (English)"),
    )
    footer_text_ur = models.CharField(
        max_length=255,
        default="تمام جملہ حقوق محفوظ ہیں۔",
        verbose_name=_("footer copyright notice (Urdu)"),
    )

    class Meta:
        verbose_name = _("landing page settings")
        verbose_name_plural = _("landing page settings")

    def __str__(self) -> str:
        return f"{self.site_title} Landing Page Settings"

    def save(self, *args, **kwargs) -> None:
        """Enforce singleton constraint by ensuring pk=1."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> LandingPageSettings:
        """Retrieve existing singleton instance or create default."""
        try:
            obj, _ = cls.objects.get_or_create(pk=1)
            return obj
        except Exception:
            return cls(pk=1)

    @property
    def embed_video_url(self) -> str:
        """Convert standard YouTube / Vimeo link to iframe embeddable URL."""
        url = (self.demo_video_url or "").strip()
        if not url:
            return ""
        if "youtube.com/watch" in url:
            import urllib.parse

            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            vid = qs.get("v", [""])[0]
            if vid:
                return f"https://www.youtube.com/embed/{vid}?autoplay=1"
        elif "youtu.be/" in url:
            vid = url.split("youtu.be/")[1].split("?")[0].split("/")[0]
            if vid:
                return f"https://www.youtube.com/embed/{vid}?autoplay=1"
        elif "vimeo.com/" in url and "player.vimeo.com" not in url:
            vid = url.split("vimeo.com/")[1].split("?")[0].split("/")[0]
            if vid:
                return f"https://player.vimeo.com/video/{vid}?autoplay=1"
        return url

    @property
    def clean_whatsapp(self) -> str:
        """Return digits only for wa.me link."""
        import re

        return re.sub(r"[^\d]", "", self.whatsapp_number or "")
