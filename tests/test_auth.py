"""tests/test_auth.py
===================
Tests for Task 2: Authentication, Roles, and 5-Attempt Account Lockout.

Coverage:
- Happy Path Login:
  - Active superadmin logs in successfully.
  - Active staff user logs in successfully.
  - Successful login resets failed_login_attempts to 0 and clears is_locked.
- Failed Login Attempts:
  - 1st to 4th failed attempts increment failed_login_attempts counter.
  - After 5th consecutive failed attempt:
    - User account becomes locked (is_locked=True, locked_until set ~15 min future).
    - Login response displays a clear lockout warning message.
  - While locked, even correct password is rejected with a message stating the account is temporarily locked.
- Lock Expiration:
  - If 15 minutes have passed (locked_until in past), user is automatically unlocked on next login attempt with correct password, resetting counters.
- Role Permissions:
  - Superadmin can access Django admin (/en/admin/) and staff management.
  - Staff user cannot access admin / staff management unless granted.
- Logout:
  - Logged-in user can log out, which terminates the session and redirects to login.
- Edge & Failure Cases:
  - Non-existent user login fails gracefully without server error.
  - Inactive user (is_active=False) cannot log in.
  - 4 failed attempts followed by 5th successful attempt resets counter and does not lock.
  - Attempt login shortly before lockout expires remains locked.
  - Expired lock with incorrect password does not authenticate.
  - Empty username or password submitted fails gracefully.
  - Unauthenticated user hitting logout handled gracefully.
"""

from datetime import timedelta

import pytest
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

User = get_user_model()


@pytest.mark.django_db
class TestHappyPathLogin:
    """Happy path authentication tests for superadmin and staff users."""

    def test_active_superadmin_login_success(self, client, superadmin_user):
        """Active superadmin logs in successfully with valid credentials."""
        login_url = reverse("accounts:login")
        response = client.post(
            login_url,
            {"username": "superadmin", "password": "TestPass123!"},
        )
        assert response.status_code == 302
        assert client.session.get("_auth_user_id") == str(superadmin_user.pk)

        superadmin_user.refresh_from_db()
        assert superadmin_user.failed_login_attempts == 0
        assert superadmin_user.is_locked is False

    def test_active_staff_user_login_success(self, client, staff_user):
        """Active staff user logs in successfully with valid credentials."""
        login_url = reverse("accounts:login")
        response = client.post(
            login_url,
            {"username": "staffuser", "password": "TestPass123!"},
        )
        assert response.status_code == 302
        assert client.session.get("_auth_user_id") == str(staff_user.pk)

        staff_user.refresh_from_db()
        assert staff_user.failed_login_attempts == 0
        assert staff_user.is_locked is False

    def test_successful_login_resets_counters_and_clears_lock(self, client, staff_user):
        """Successful login resets failed_login_attempts to 0 and clears is_locked."""
        staff_user.failed_login_attempts = 3
        staff_user.is_locked = False
        staff_user.save()

        login_url = reverse("accounts:login")
        response = client.post(
            login_url,
            {"username": staff_user.username, "password": "TestPass123!"},
        )
        assert response.status_code == 302
        assert client.session.get("_auth_user_id") == str(staff_user.pk)

        staff_user.refresh_from_db()
        assert staff_user.failed_login_attempts == 0
        assert staff_user.is_locked is False
        assert staff_user.locked_until is None


@pytest.mark.django_db
class TestAccountLockout:
    """Tests for 5-attempt failed login lockout mechanism."""

    def test_failed_attempts_increment_counter_one_through_four(self, client, staff_user):
        """1st to 4th failed attempts increment failed_login_attempts counter without locking."""
        login_url = reverse("accounts:login")

        for attempt in range(1, 5):
            response = client.post(
                login_url,
                {"username": staff_user.username, "password": f"WrongPass{attempt}"},
            )
            assert response.status_code == 200
            assert "_auth_user_id" not in client.session

            staff_user.refresh_from_db()
            assert staff_user.failed_login_attempts == attempt
            assert staff_user.is_locked is False
            assert staff_user.locked_until is None

    def test_fifth_consecutive_failed_attempt_locks_account(self, client, staff_user):
        """After 5th consecutive failed attempt, account is locked for ~15 minutes with warning."""
        login_url = reverse("accounts:login")
        staff_user.failed_login_attempts = 4
        staff_user.save()

        before_attempt = timezone.now()
        response = client.post(
            login_url,
            {"username": staff_user.username, "password": "WrongPassword5"},
            follow=True,
        )

        staff_user.refresh_from_db()
        assert staff_user.failed_login_attempts >= 5
        assert staff_user.is_locked is True
        assert staff_user.locked_until is not None

        # Lock duration is approximately 15 minutes in the future
        expected_min = before_attempt + timedelta(minutes=14)
        expected_max = before_attempt + timedelta(minutes=16)
        assert expected_min <= staff_user.locked_until <= expected_max

        # Response displays a clear lockout warning message
        content = response.content.decode().lower()
        messages_text = " ".join(
            str(m).lower() for m in messages.get_messages(response.wsgi_request)
        )
        assert "lock" in content or "lock" in messages_text

    def test_locked_account_rejects_correct_password(self, client, staff_user):
        """While locked, even correct password is rejected with a lockout message."""
        staff_user.is_locked = True
        staff_user.failed_login_attempts = 5
        staff_user.locked_until = timezone.now() + timedelta(minutes=15)
        staff_user.save()

        login_url = reverse("accounts:login")
        response = client.post(
            login_url,
            {"username": staff_user.username, "password": "TestPass123!"},
            follow=True,
        )

        assert "_auth_user_id" not in client.session
        staff_user.refresh_from_db()
        assert staff_user.is_locked is True

        content = response.content.decode().lower()
        messages_text = " ".join(
            str(m).lower() for m in messages.get_messages(response.wsgi_request)
        )
        assert "lock" in content or "lock" in messages_text

    def test_lock_expiration_unlocks_account_on_correct_password(self, client, staff_user):
        """If 15 minutes have passed, user is automatically unlocked on login with correct password."""
        staff_user.is_locked = True
        staff_user.failed_login_attempts = 5
        staff_user.locked_until = timezone.now() - timedelta(minutes=16)
        staff_user.save()

        login_url = reverse("accounts:login")
        response = client.post(
            login_url,
            {"username": staff_user.username, "password": "TestPass123!"},
            follow=True,
        )

        staff_user.refresh_from_db()
        assert staff_user.is_locked is False
        assert staff_user.failed_login_attempts == 0
        assert staff_user.locked_until is None or staff_user.locked_until <= timezone.now()

        assert client.session.get("_auth_user_id") == str(staff_user.pk)
        assert response.status_code == 200


@pytest.mark.django_db
class TestAuthEdgeCases:
    """Edge cases and failure cases for authentication and lockout."""

    def test_nonexistent_username_fails_gracefully(self, client):
        """Non-existent username fails gracefully without server error."""
        login_url = reverse("accounts:login")
        response = client.post(
            login_url,
            {"username": "nonexistent_user_999", "password": "AnyPassword123!"},
        )
        assert response.status_code == 200
        assert "_auth_user_id" not in client.session

    def test_inactive_user_cannot_login(self, client, staff_user):
        """Inactive user (is_active=False) cannot log in even with correct credentials."""
        staff_user.is_active = False
        staff_user.save()

        login_url = reverse("accounts:login")
        response = client.post(
            login_url,
            {"username": staff_user.username, "password": "TestPass123!"},
        )
        assert response.status_code in (200, 302)
        assert "_auth_user_id" not in client.session

    def test_four_failed_attempts_then_success_does_not_lock(self, client, staff_user):
        """4 failed attempts followed by 5th successful attempt resets counter and does not lock."""
        login_url = reverse("accounts:login")
        for i in range(1, 5):
            client.post(
                login_url,
                {"username": staff_user.username, "password": f"BadPassword{i}"},
            )

        staff_user.refresh_from_db()
        assert staff_user.failed_login_attempts == 4
        assert staff_user.is_locked is False

        # 5th attempt is valid password
        response = client.post(
            login_url,
            {"username": staff_user.username, "password": "TestPass123!"},
        )
        assert response.status_code == 302
        assert client.session.get("_auth_user_id") == str(staff_user.pk)

        staff_user.refresh_from_db()
        assert staff_user.failed_login_attempts == 0
        assert staff_user.is_locked is False

    def test_login_attempt_just_before_lockout_expires_remains_locked(self, client, staff_user):
        """Login attempt seconds before lockout expiration is still rejected."""
        staff_user.is_locked = True
        staff_user.failed_login_attempts = 5
        staff_user.locked_until = timezone.now() + timedelta(seconds=15)
        staff_user.save()

        login_url = reverse("accounts:login")
        response = client.post(
            login_url,
            {"username": staff_user.username, "password": "TestPass123!"},
            follow=True,
        )
        assert response.status_code == 200
        assert "_auth_user_id" not in client.session
        staff_user.refresh_from_db()
        assert staff_user.is_locked is True

    def test_lock_expired_with_incorrect_password_does_not_authenticate(self, client, staff_user):
        """Lock expired in past, but user submits incorrect password — must not log in."""
        staff_user.is_locked = True
        staff_user.failed_login_attempts = 5
        staff_user.locked_until = timezone.now() - timedelta(minutes=20)
        staff_user.save()

        login_url = reverse("accounts:login")
        response = client.post(
            login_url,
            {"username": staff_user.username, "password": "WrongPasswordAgain"},
        )
        assert response.status_code == 200
        assert "_auth_user_id" not in client.session

    def test_empty_credentials_rejected_gracefully(self, client):
        """Submitting empty username and password returns form errors without 500."""
        login_url = reverse("accounts:login")
        response = client.post(
            login_url,
            {"username": "", "password": ""},
        )
        assert response.status_code == 200
        assert "_auth_user_id" not in client.session


@pytest.mark.django_db
class TestRolePermissions:
    """Permission verification between Superadmin and Staff users."""

    def test_superadmin_can_access_django_admin(self, superadmin_client):
        """Superadmin can access Django admin panel (/en/admin/)."""
        response = superadmin_client.get("/en/admin/")
        assert response.status_code == 200

    def test_superadmin_can_access_staff_management(self, superadmin_client):
        """Superadmin can access staff/user management in Django admin."""
        response = superadmin_client.get("/en/admin/accounts/user/")
        assert response.status_code == 200

    def test_staff_user_cannot_access_django_admin(self, staff_client):
        """Staff user without staff status is denied access to Django admin."""
        response = staff_client.get("/en/admin/")
        assert response.status_code in (302, 403)
        if response.status_code == 302:
            assert "/admin/login" in response.url

    def test_staff_user_cannot_access_staff_management(self, staff_client):
        """Staff user without privileges cannot access staff/user management."""
        response = staff_client.get("/en/admin/accounts/user/")
        assert response.status_code in (302, 403)


@pytest.mark.django_db
class TestLogout:
    """Logout functionality and session termination tests."""

    def test_authenticated_user_logout_clears_session_and_redirects(self, client, staff_user):
        """Logged-in user logs out, which terminates the session and redirects to login."""
        client.force_login(staff_user)
        assert client.session.get("_auth_user_id") == str(staff_user.pk)

        logout_url = reverse("accounts:logout")
        response = client.post(logout_url, follow=True)

        assert "_auth_user_id" not in client.session
        assert response.status_code == 200
        login_url = reverse("accounts:login")
        assert login_url in response.request.get(
            "PATH_INFO", ""
        ) or "login" in response.request.get("PATH_INFO", "")

    def test_unauthenticated_user_logout_handled_gracefully(self, client):
        """Unauthenticated user hitting logout URL is handled gracefully."""
        logout_url = reverse("accounts:logout")
        response = client.post(logout_url, follow=True)
        assert response.status_code == 200
