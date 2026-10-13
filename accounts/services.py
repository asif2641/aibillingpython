"""
accounts/services.py
====================
Authentication business logic for the accounts app.

Handles tracking failed login attempts, applying 5-attempt account lockout
with 15-minute duration, automatic lock expiry and unlock, and resetting
counters on successful login.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

if TYPE_CHECKING:
    from accounts.models import User

MAX_FAILED_LOGIN_ATTEMPTS: int = 5
LOCKOUT_DURATION_MINUTES: int = 15


def is_account_locked(user: User) -> bool:
    """Check whether a user account is locked.

    If the lock timestamp has passed (locked_until <= now), the lock is
    automatically cleared and the failed attempts counter is reset to 0.

    Args:
        user: The User instance to check.

    Returns:
        True if the account is currently locked, False otherwise.
    """
    if user.is_locked:
        now = timezone.now()
        if user.locked_until is not None and now >= user.locked_until:
            user.is_locked = False
            user.locked_until = None
            user.failed_login_attempts = 0
            user.save(update_fields=["is_locked", "locked_until", "failed_login_attempts"])
            return False
        return True
    return False


def record_failed_login(user: User) -> None:
    """Record a failed login attempt for the user.

    Increments the failed login attempt counter. If the counter reaches
    or exceeds 5 attempts, locks the account for 15 minutes.

    Args:
        user: The User instance that failed to authenticate.
    """
    now = timezone.now()
    user.failed_login_attempts += 1
    user.last_login_attempt = now

    if user.failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
        user.is_locked = True
        user.locked_until = now + timedelta(minutes=LOCKOUT_DURATION_MINUTES)

    user.save(
        update_fields=[
            "failed_login_attempts",
            "last_login_attempt",
            "is_locked",
            "locked_until",
        ]
    )


def record_successful_login(user: User) -> None:
    """Record a successful login for the user.

    Resets the failed attempts counter to 0, clears any lock status and
    locked_until timestamp, and updates last_login_attempt.

    Args:
        user: The User instance that authenticated successfully.
    """
    user.failed_login_attempts = 0
    user.is_locked = False
    user.locked_until = None
    user.last_login_attempt = timezone.now()
    user.save(
        update_fields=[
            "failed_login_attempts",
            "is_locked",
            "locked_until",
            "last_login_attempt",
        ]
    )


def create_staff_user(
    username: str,
    password: str,
    email: str = "",
    first_name: str = "",
    last_name: str = "",
    can_delete_records: bool = False,
    can_manage_shop: bool = False,
    can_manage_categories: bool = False,
) -> User:
    """Create and return a new staff member with role='staff' and granular permissions."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        role=User.Role.STAFF,
        can_delete_records=can_delete_records,
        can_manage_shop=can_manage_shop,
        can_manage_categories=can_manage_categories,
    )


def toggle_staff_status(target_user: User, actor_user: User) -> bool:
    """Toggle the active status of target_user. Superadmins cannot deactivate themselves.

    Returns True if toggled, False if rejected (e.g. self-deactivation).
    """
    if target_user.pk == actor_user.pk:
        return False
    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=["is_active"])
    return True


def update_staff_permissions(
    target_user: User,
    can_delete_records: bool = False,
    can_manage_shop: bool = False,
    can_manage_categories: bool = False,
) -> User:
    """Update granular permission flags for target_user."""
    target_user.can_delete_records = can_delete_records
    target_user.can_manage_shop = can_manage_shop
    target_user.can_manage_categories = can_manage_categories
    target_user.save(
        update_fields=["can_delete_records", "can_manage_shop", "can_manage_categories"]
    )
    return target_user


def reset_staff_password(target_user: User, new_password: str) -> User:
    """Reset staff user password, clear lockout flags and reset failed attempts."""
    target_user.set_password(new_password)
    target_user.failed_login_attempts = 0
    target_user.is_locked = False
    target_user.locked_until = None
    target_user.save(
        update_fields=["password", "failed_login_attempts", "is_locked", "locked_until"]
    )
    return target_user
