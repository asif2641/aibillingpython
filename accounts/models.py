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

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STAFF,
        verbose_name=_("role"),
        help_text=_("Determines what actions this user can perform."),
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
