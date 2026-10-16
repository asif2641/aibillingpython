"""parties/models.py
=================
Party model representing vendors, customers, or entities that act as both.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class Party(models.Model):
    """Vendor, customer, or dual-role commercial entity."""

    class PartyType(models.TextChoices):
        VENDOR = "vendor", _("Vendor")
        CUSTOMER = "customer", _("Customer")
        BOTH = "both", _("Both")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="parties",
        verbose_name=_("owner"),
        help_text=_("Business account that owns this party."),
    )

    name = models.CharField(
        max_length=255,
        verbose_name=_("name"),
        help_text=_("Primary business or individual name."),
    )
    urdu_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Urdu name"),
        help_text=_("Optional Urdu translation or name in Nastaliq/Arabic script."),
    )
    phone = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name=_("phone number"),
        help_text=_("Contact phone number."),
    )
    email = models.EmailField(
        blank=True,
        default="",
        verbose_name=_("email address"),
        help_text=_("Optional contact email address."),
    )
    address = models.TextField(
        blank=True,
        default="",
        verbose_name=_("address"),
        help_text=_("Physical address or market location."),
    )
    tax_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("tax/NTN/STRN number"),
        help_text=_("National Tax Number or Sales Tax Registration Number."),
    )
    party_type = models.CharField(
        max_length=20,
        choices=PartyType.choices,
        default=PartyType.VENDOR,
        verbose_name=_("party type"),
        help_text=_("Role of this party: vendor, customer, or both."),
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name=_("notes"),
        help_text=_("Internal remarks or terms for this party."),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("is active"),
        help_text=_("Designates whether this party is currently active."),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("party")
        verbose_name_plural = _("parties")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["party_type"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["is_active"]),
        ]

    def clean(self) -> None:
        """Validate party fields."""
        super().clean()
        if not self.name or not self.name.strip():
            raise ValidationError({"name": _("Party name is required.")})

    def save(self, *args, **kwargs):
        """Clean and persist the party instance."""
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.get_party_type_display()})"
