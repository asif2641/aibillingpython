"""
accounts/models.py
===================
Custom User model for the aibilling project.

We extend Django's AbstractUser so we keep all built-in fields
(username, password, email, first_name, last_name, is_active, etc.)
and add our own role and security fields.

Always reference the user model via settings.AUTH_USER_MODEL or
get_user_model() — never import User directly.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """Extended user model with role-based access control and login security.

    Roles:
        superadmin — full access: manage staff, delete data, change shop settings.
        staff      — upload/scan bills, view reports. Specific permissions can be
                     granted by a superadmin.

    Security fields track failed login attempts so the account can be locked
    automatically after repeated failures (handled in the auth service layer).
    """

    class Role(models.TextChoices):
        """Allowed user roles. Add new roles here — never use raw strings."""

        SUPERADMIN = "superadmin", _("Super Admin")
        STAFF = "staff", _("Staff")

    class Plan(models.TextChoices):
        """SaaS subscription plans."""

        FREE = "free", _("Free Trial")
        PRO = "pro", _("Pro")
        BUSINESS = "business", _("Business")

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STAFF,
        verbose_name=_("role"),
        help_text=_("Determines what actions this user can perform."),
    )

    plan = models.CharField(
        max_length=20,
        choices=Plan.choices,
        default=Plan.FREE,
        verbose_name=_("subscription plan"),
        help_text=_("Current SaaS subscription plan tier."),
    )

    business_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("business / shop name"),
        help_text=_("Primary commercial or shop identity."),
    )

    monthly_scan_quota = models.PositiveIntegerField(
        default=10,
        verbose_name=_("monthly scan quota"),
        help_text=_("Maximum AI bill scans allowed in the current billing cycle."),
    )

    scans_used_this_month = models.PositiveIntegerField(
        default=0,
        verbose_name=_("scans used this month"),
        help_text=_("Number of scans consumed in the current billing cycle."),
    )

    quota_reset_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("quota reset date"),
        help_text=_("Next date when monthly scan counter resets."),
    )

    is_locked = models.BooleanField(
        default=False,
        verbose_name=_("account locked"),
        help_text=_(
            "When True the user cannot log in. " "Set automatically after too many failed attempts."
        ),
    )

    locked_until = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("locked until"),
        help_text=_("The account lock is automatically lifted after this datetime (UTC)."),
    )

    failed_login_attempts = models.IntegerField(
        default=0,
        verbose_name=_("failed login attempts"),
        help_text=_("Counter reset to 0 on successful login."),
    )

    last_login_attempt = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("last login attempt"),
        help_text=_("Datetime (UTC) of the most recent login attempt, successful or not."),
    )

    can_delete_records = models.BooleanField(
        default=False,
        verbose_name=_("can delete records"),
        help_text=_("Staff member can delete bills and records."),
    )

    can_manage_shop = models.BooleanField(
        default=False,
        verbose_name=_("can manage shop"),
        help_text=_("Staff member can update shop profile and settings."),
    )

    can_manage_categories = models.BooleanField(
        default=False,
        verbose_name=_("can manage categories"),
        help_text=_("Staff member can create and modify product categories and units."),
    )

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["username"]

    def __str__(self) -> str:
        return f"{self.username} ({self.get_role_display()})"

    # ──────────────────────────────────────────────────────────────────────────
    # Convenience helpers
    # ──────────────────────────────────────────────────────────────────────────

    @property
    def is_superadmin(self) -> bool:
        """Return True if this user has the Super Admin role."""
        return self.role == self.Role.SUPERADMIN

    @property
    def is_staff_member(self) -> bool:
        """Return True if this user has the Staff role."""
        return self.role == self.Role.STAFF

    @property
    def has_scans_remaining(self) -> bool:
        """Return True if user has scans remaining in the current cycle."""
        if self.is_superuser:
            return True
        return self.scans_used_this_month < self.monthly_scan_quota

    @property
    def remaining_scans(self) -> int:
        """Return remaining scans count."""
        if self.is_superuser:
            return 9999
        return max(0, self.monthly_scan_quota - self.scans_used_this_month)

    def increment_scans_used(self) -> int:
        """Increment scans consumed counter and persist."""
        self.scans_used_this_month += 1
        self.save(update_fields=["scans_used_this_month"])
        return self.scans_used_this_month


class SubscriptionPaymentRequest(models.Model):
    """Model tracking tenant payment submissions for plan upgrades."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending Verification")
        APPROVED = "approved", _("Approved & Activated")
        REJECTED = "rejected", _("Rejected")

    class PaymentMethod(models.TextChoices):
        BANK_TRANSFER = "bank_transfer", _("Bank Transfer / Raast")
        JAZZCASH = "jazzcash", _("JazzCash")
        EASYPAISA = "easypaisa", _("EasyPaisa")
        OTHER = "other", _("Other / Cash")

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="payment_requests",
        verbose_name=_("tenant"),
    )
    plan = models.CharField(
        max_length=20,
        choices=User.Plan.choices,
        verbose_name=_("requested plan"),
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("amount (PKR)"),
    )
    payment_method = models.CharField(
        max_length=30,
        choices=PaymentMethod.choices,
        default=PaymentMethod.BANK_TRANSFER,
        verbose_name=_("payment method"),
    )
    transaction_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("transaction ID / TID"),
    )
    receipt_image = models.ImageField(
        upload_to="payment_proofs/%Y/%m/",
        blank=True,
        null=True,
        verbose_name=_("payment proof screenshot"),
    )
    customer_notes = models.TextField(
        blank=True,
        default="",
        verbose_name=_("customer notes"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name=_("status"),
    )
    admin_notes = models.TextField(
        blank=True,
        default="",
        verbose_name=_("admin notes / rejection reason"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name=_("submitted at"),
    )
    reviewed_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("reviewed at"),
    )
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reviewed_payment_requests",
        verbose_name=_("reviewed by"),
    )

    class Meta:
        verbose_name = _("subscription payment request")
        verbose_name_plural = _("subscription payment requests")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.get_plan_display()} ({self.get_status_display()})"
