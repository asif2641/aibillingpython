"""
settings_app/models.py
======================
Shop profile and application settings models.

Implements the ShopProfile singleton model holding business identity,
tax, localization, receipt footer, and scanning limit settings.
"""

from __future__ import annotations

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
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
