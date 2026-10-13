"""ledger/models.py
================
Payment and ledger transaction models.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Payment(models.Model):
    """Payment record against a party account or allocated to a specific bill."""

    class PaymentMethod(models.TextChoices):
        CASH = "cash", _("Cash")
        BANK_TRANSFER = "bank_transfer", _("Bank Transfer")
        CHEQUE = "cheque", _("Cheque")
        ONLINE = "online", _("Online")

    party = models.ForeignKey(
        "parties.Party",
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=_("party"),
    )
    bill = models.ForeignKey(
        "bills.Bill",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments",
        verbose_name=_("bill"),
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_("amount"),
    )
    payment_date = models.DateField(
        default=timezone.now,
        verbose_name=_("payment date"),
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
        verbose_name=_("payment method"),
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("reference / cheque / receipt #"),
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name=_("notes"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_payments",
        verbose_name=_("created by"),
    )
    is_deleted = models.BooleanField(
        default=False,
        verbose_name=_("is deleted"),
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("deleted at"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ["-payment_date", "-id"]
        indexes = [
            models.Index(fields=["payment_date"]),
            models.Index(fields=["party"]),
            models.Index(fields=["bill"]),
            models.Index(fields=["payment_method"]),
            models.Index(fields=["is_deleted"]),
        ]

    def __str__(self) -> str:
        ref = self.reference or f"#{self.pk}"
        return f"Payment {ref} - {self.party.name} ({self.amount})"

    def clean(self) -> None:
        super().clean()
        if self.amount is not None and self.amount <= Decimal("0.00"):
            raise ValidationError({"amount": _("Amount must be greater than zero.")})
