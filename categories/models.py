"""
categories/models.py
====================
Category and Unit models for bill classification and unit of measure.
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

HEX_COLOR_REGEX = r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$"

hex_color_validator = RegexValidator(
    regex=HEX_COLOR_REGEX,
    message=_("Enter a valid hex color code (e.g. #3B82F6)."),
)


class Category(models.Model):
    """Product/service category for classifying billing items."""

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("category name"),
        help_text=_("English or primary name of the category."),
    )

    urdu_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Urdu name"),
        help_text=_("Optional Urdu translation of category name."),
    )

    color = models.CharField(
        max_length=20,
        default="#3B82F6",
        validators=[hex_color_validator],
        verbose_name=_("color hex code"),
        help_text=_("Hexadecimal color code for badges and charts (e.g. #3B82F6)."),
    )

    is_archived = models.BooleanField(
        default=False,
        verbose_name=_("archived"),
        help_text=_("Archived categories are hidden from new bill item creation."),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if not self.color or not re.match(HEX_COLOR_REGEX, self.color):
            raise ValidationError({"color": _("Enter a valid hex color code (e.g. #3B82F6).")})

    @classmethod
    def seed_defaults(cls):
        """Seed default product categories."""
        from categories.services import seed_default_categories

        return seed_default_categories()


class Unit(models.Model):
    """Unit of measurement for products and invoice line items."""

    name = models.CharField(
        max_length=50,
        verbose_name=_("unit name"),
        help_text=_("Display name of unit (e.g. Pieces, Kilogram)."),
    )

    code = models.CharField(
        max_length=20,
        unique=True,
        verbose_name=_("unit code"),
        help_text=_("Abbreviated unit code (e.g. pcs, kg, ltr)."),
    )

    urdu_name = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name=_("Urdu name"),
        help_text=_("Urdu translation of the unit (e.g. کلوگرام)."),
    )

    is_system = models.BooleanField(
        default=False,
        verbose_name=_("system unit"),
        help_text=_("Built-in standard unit that cannot be deleted."),
    )

    class Meta:
        verbose_name = _("unit")
        verbose_name_plural = _("units")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    @classmethod
    def seed_defaults(cls):
        """Seed standard units of measurement."""
        from categories.services import seed_default_units

        return seed_default_units()
