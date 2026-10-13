"""bills/models.py
===============
Bill and BillItem models representing purchase and sales invoices.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# SQLite Decimal converter patch to preserve fractional unit prices without truncating
try:
    from django.db.backends.sqlite3 import operations

    _orig_get_decimalfield_converter = operations.DatabaseOperations.get_decimalfield_converter

    def _patched_get_decimalfield_converter(self, expression):
        output_field = getattr(expression, "output_field", None)
        if getattr(output_field, "_preserve_fractional", False):
            return lambda value, expr, conn: Decimal(str(value)) if value is not None else None
        return _orig_get_decimalfield_converter(self, expression)

    operations.DatabaseOperations.get_decimalfield_converter = _patched_get_decimalfield_converter
except (ImportError, AttributeError):
    pass


class UnitPriceField(models.DecimalField):
    """DecimalField for unit prices that preserves fractional precision when saving to SQLite."""

    _preserve_fractional = True

    def get_db_prep_save(self, value, connection):
        if hasattr(value, "as_sql"):
            return value
        val = self.to_python(value)
        if val is None:
            return None
        places = max(
            self.decimal_places,
            -val.as_tuple().exponent if val.as_tuple().exponent < 0 else 0,
        )
        return connection.ops.adapt_decimalfield_value(val, self.max_digits, places)


class BillQuerySet(models.QuerySet):
    """QuerySet providing soft delete filter helpers."""

    def active(self):
        return self.filter(is_deleted=False)

    def trashed(self):
        return self.filter(is_deleted=True)


class ActiveBillManager(models.Manager.from_queryset(BillQuerySet)):
    """Default manager filtering out soft-deleted bills."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class Bill(models.Model):
    """Invoice / receipt record for purchases and sales."""

    class BillType(models.TextChoices):
        PURCHASE = "purchase", _("Purchase")
        SALE = "sale", _("Sale")

    class Status(models.TextChoices):
        DRAFT = "Draft", _("Draft")
        NEEDS_REVIEW = "NeedsReview", _("Needs Review")
        VERIFIED = "Verified", _("Verified")

    class Source(models.TextChoices):
        MANUAL = "manual", _("Manual")
        SCAN = "scan", _("Scan")

    class PaymentStatus(models.TextChoices):
        UNPAID = "Unpaid", _("Unpaid")
        PARTIALLY_PAID = "Partially Paid", _("Partially Paid")
        PAID = "Paid", _("Paid")

    bill_type = models.CharField(
        max_length=20,
        choices=BillType.choices,
        default=BillType.PURCHASE,
        verbose_name=_("bill type"),
    )
    party = models.ForeignKey(
        "parties.Party",
        on_delete=models.PROTECT,
        related_name="bills",
        verbose_name=_("party"),
    )
    invoice_no = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("invoice number"),
    )
    bill_date = models.DateField(
        default=timezone.now,
        verbose_name=_("bill date"),
    )
    bill_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name=_("bill time"),
    )
    category = models.ForeignKey(
        "categories.Category",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bills",
        verbose_name=_("category"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.VERIFIED,
        blank=True,
        verbose_name=_("verification status"),
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.MANUAL,
        verbose_name=_("entry source"),
    )
    subtotal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("subtotal"),
    )
    discount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("discount"),
    )
    tax = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("tax"),
    )
    grand_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("grand total"),
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
        verbose_name=_("payment status"),
    )
    amount_paid = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("amount paid"),
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
        related_name="created_bills",
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

    # Managers
    objects = ActiveBillManager()
    active_objects = ActiveBillManager()
    all_objects = models.Manager.from_queryset(BillQuerySet)()

    class Meta:
        verbose_name = _("bill")
        verbose_name_plural = _("bills")
        ordering = ["-bill_date", "-id"]
        base_manager_name = "all_objects"
        indexes = [
            models.Index(fields=["bill_date"]),
            models.Index(fields=["party"]),
            models.Index(fields=["category"]),
            models.Index(fields=["invoice_no"]),
            models.Index(fields=["payment_status"]),
            models.Index(fields=["is_deleted"]),
        ]

    def __str__(self) -> str:
        inv = self.invoice_no or f"Bill #{self.pk}"
        party_name = self.party.name if hasattr(self, "party") and self.party else ""
        return f"{inv} - {party_name} ({self.grand_total})"

    def clean(self) -> None:
        super().clean()
        if self.discount < Decimal("0.00"):
            raise ValidationError({"discount": _("Discount cannot be negative.")})
        if self.tax < Decimal("0.00"):
            raise ValidationError({"tax": _("Tax cannot be negative.")})


class BillItem(models.Model):
    """Line item on a bill."""

    bill = models.ForeignKey(
        Bill,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("bill"),
    )
    serial_no = models.PositiveIntegerField(
        default=1,
        verbose_name=_("serial number"),
    )
    item_name = models.CharField(
        max_length=255,
        verbose_name=_("item name"),
    )
    urdu_item_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Urdu item name"),
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("1.0000"),
        verbose_name=_("quantity"),
    )
    unit = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name=_("unit of measure"),
    )
    unit_price = UnitPriceField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("unit price"),
    )
    line_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("line total"),
    )

    class Meta:
        verbose_name = _("bill item")
        verbose_name_plural = _("bill items")
        ordering = ["serial_no", "id"]
        indexes = [
            models.Index(fields=["item_name"]),
        ]

    def clean(self) -> None:
        super().clean()
        if self.urdu_item_name is None:
            self.urdu_item_name = ""
        if self.unit is None:
            self.unit = ""

    def save(self, *args, **kwargs):
        if self.urdu_item_name is None:
            self.urdu_item_name = ""
        if self.unit is None:
            self.unit = ""
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.item_name} ({self.quantity} {self.unit})".strip()
