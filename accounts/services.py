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
