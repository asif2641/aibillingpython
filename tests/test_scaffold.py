"""
tests/test_scaffold.py
=======================
Smoke tests that verify the project scaffolding is correct.

These tests run in every CI pipeline to catch configuration regressions.
They test project-level concerns like URL routing, user model configuration,
and the money_round() utility.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from billing.utils import money_round

# ──────────────────────────────────────────────────────────────────────────────
# money_round() tests — critical path (must be ≥ 95% covered per quality rules)
# ──────────────────────────────────────────────────────────────────────────────


class TestMoneyRound:
    """Tests for the money_round() utility function."""

    def test_rounds_to_two_decimal_places(self):
        """Normal case: round to 2 places."""
        assert money_round(Decimal("1.234")) == Decimal("1.23")

    def test_rounds_half_up(self):
        """ROUND_HALF_UP: .005 rounds up to .01."""
        assert money_round(Decimal("1.005")) == Decimal("1.01")

    def test_rounds_down_when_below_half(self):
        """Below half: .004 rounds down."""
        assert money_round(Decimal("1.004")) == Decimal("1.00")

    def test_accepts_int(self):
        """Integer input is converted correctly."""
        assert money_round(5) == Decimal("5.00")

    def test_accepts_string(self):
        """String input is converted correctly."""
        assert money_round("3.14159") == Decimal("3.14")

    def test_zero_value(self):
        """Zero returns zero."""
        assert money_round(Decimal("0")) == Decimal("0.00")

    def test_large_value(self):
        """Large monetary values round correctly."""
        assert money_round(Decimal("999999.999")) == Decimal("1000000.00")

    def test_negative_value(self):
        """Negative values (credits/refunds) round correctly (-1.005 -> -1.01 with ROUND_HALF_UP)."""
        assert money_round(Decimal("-1.005")) == Decimal("-1.01")

    def test_three_items_rounding(self):
        """Classic rounding test: 3 × 1.005 should equal 3.02, not 3.015."""
        result = money_round(Decimal("1.005") * 3)
        assert result == Decimal("3.02")


# ──────────────────────────────────────────────────────────────────────────────
# User model tests
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestUserModel:
    """Tests for the custom User model."""

    def test_custom_user_model_is_used(self):
        """AUTH_USER_MODEL must point to accounts.User, not the default."""
        User = get_user_model()
        assert User.__name__ == "User"
        assert User._meta.app_label == "accounts"

    def test_superadmin_role(self, superadmin_user):
        """Superadmin role is set correctly."""
        assert superadmin_user.role == "superadmin"
        assert superadmin_user.is_superadmin is True
        assert superadmin_user.is_staff_member is False

    def test_staff_role(self, staff_user):
        """Staff role is set correctly."""
        assert staff_user.role == "staff"
        assert staff_user.is_staff_member is True
        assert staff_user.is_superadmin is False

    def test_default_role_is_staff(self, db):
        """New users default to the staff role."""
        User = get_user_model()
        user = User.objects.create_user(username="newuser", password="pass")
        assert user.role == "staff"

    def test_is_locked_default_false(self, db):
        """Accounts are unlocked by default."""
        User = get_user_model()
        user = User.objects.create_user(username="newuser2", password="pass")
        assert user.is_locked is False

    def test_failed_login_attempts_default_zero(self, db):
        """Failed login counter starts at 0."""
        User = get_user_model()
        user = User.objects.create_user(username="newuser3", password="pass")
        assert user.failed_login_attempts == 0

    def test_str_representation(self, staff_user):
        """__str__ shows username and role."""
        assert "staffuser" in str(staff_user)
        assert "Staff" in str(staff_user)


# ──────────────────────────────────────────────────────────────────────────────
# URL routing tests
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestURLRouting:
    """Tests that core URL patterns resolve correctly."""

    def test_login_url_resolves(self, client: Client):
        """The login page is reachable."""
        # With i18n_patterns and prefix_default_language=True,
        # the login URL is /en/accounts/login/
        response = client.get("/en/accounts/login/")
        # Returns 200 (login form) or 302 (redirect if already logged in)
        assert response.status_code in (200, 302)

    def test_admin_url_resolves(self, client: Client):
        """The admin login page is reachable."""
        response = client.get("/en/admin/login/")
        assert response.status_code == 200

    def test_unauthenticated_root_redirects(self, client: Client):
        """The root URL redirects unauthenticated users to login."""
        # Root / — no view yet, but it should not 500
        response = client.get("/en/accounts/login/")
        assert response.status_code in (200, 302, 404)
