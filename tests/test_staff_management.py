"""tests/test_staff_management.py
==============================
Tests for Phase 2: Staff Management and Granular Permissions.

Coverage:
- Staff Listing:
  - Superadmin can GET /en/settings/staff/ to view the list of staff accounts.
  - Staff list displays username, email, active status, and permission flags.
  - Unauthenticated access redirects to login.
  - Non-superadmin staff users are denied access (HTTP 403 or redirect).
- Staff Creation:
  - Superadmin can POST /en/settings/staff/add/ to create a new staff user.
  - Support for permission checkboxes: can_delete_records, can_manage_shop, can_manage_categories.
  - Newly created staff user has role='staff', properly hashed password, and correct flags.
  - Validation: duplicate username rejected, password confirmation mismatch rejected,
    empty fields rejected.
  - Staff users cannot access or POST to /en/settings/staff/add/.
- Staff Status Toggle:
  - Superadmin can POST /en/settings/staff/<id>/toggle-status/ to enable or disable staff.
  - Disabled staff member cannot log in.
  - Self-deactivation prevention: Superadmin cannot disable their own account.
  - Non-existent staff ID returns HTTP 404.
  - Non-superadmin staff cannot toggle status.
- Staff Permissions Update:
  - Superadmin can POST /en/settings/staff/<id>/permissions/ to update permission checkboxes.
  - Permissions are updated in the database accordingly.
  - Non-superadmin staff cannot update permissions.
  - Non-existent staff ID returns HTTP 404.
- Staff Password Reset:
  - Superadmin can POST /en/settings/staff/<id>/reset-password/ to set a new password.
  - Password is updated and hashed.
  - Resetting password unlocks locked accounts and resets failed login attempts.
  - Password mismatch rejected.
  - Non-superadmin staff cannot reset passwords.
  - Non-existent staff ID returns HTTP 404.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.fixture
def target_staff(db):
    """A baseline active staff member with no elevated permissions."""
    return User.objects.create_user(
        username="john_cashier",
        email="john@example.com",
        password="InitialStaffPass123!",
        role=User.Role.STAFF,
        first_name="John",
        last_name="Cashier",
    )


@pytest.fixture
def locked_staff(db):
    """A staff member locked out due to excessive failed login attempts."""
    user = User.objects.create_user(
        username="locked_user",
        email="locked@example.com",
        password="LockedPass123!",
        role=User.Role.STAFF,
    )
    user.is_locked = True
    user.failed_login_attempts = 5
    user.save()
    return user


@pytest.mark.django_db
class TestStaffListing:
    """Tests for viewing the staff management roster at /en/settings/staff/."""

    STAFF_LIST_URL = "/en/settings/staff/"

    def test_superadmin_can_view_staff_list(self, superadmin_client, target_staff):
        """Superadmin can GET /en/settings/staff/ and see staff members."""
        response = superadmin_client.get(self.STAFF_LIST_URL)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert target_staff.username in content

    def test_staff_list_displays_multiple_staff_members(self, superadmin_client, target_staff):
        """Staff list view displays all configured staff members."""
        staff_two = User.objects.create_user(
            username="mary_accountant",
            email="mary@example.com",
            password="TestPass123!",
            role=User.Role.STAFF,
        )
        response = superadmin_client.get(self.STAFF_LIST_URL)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert target_staff.username in content
        assert staff_two.username in content

    def test_unauthenticated_user_redirected_from_staff_list(self, client):
        """Unauthenticated visitor is redirected to the login page."""
        response = client.get(self.STAFF_LIST_URL)
        assert response.status_code == 302
        assert "/login" in response.url or reverse("accounts:login") in response.url

    def test_regular_staff_denied_access_to_staff_list(self, staff_client):
        """Regular staff user cannot view the staff management roster."""
        # Ensure staff endpoint exists
        list_resp = staff_client.get(self.STAFF_LIST_URL)
        assert list_resp.status_code in [403, 302]

    def test_staff_with_other_permissions_denied_staff_list(self, client, db):
        """Even staff with can_manage_shop or can_manage_categories cannot view staff list."""
        user = User.objects.create_user(
            username="privileged_staff",
            email="priv@example.com",
            password="TestPass123!",
            role=User.Role.STAFF,
        )
        if hasattr(user, "can_manage_shop"):
            user.can_manage_shop = True
            user.save()

        client.force_login(user)
        response = client.get(self.STAFF_LIST_URL)
        assert response.status_code in [403, 302]


@pytest.mark.django_db
class TestStaffCreation:
    """Tests for creating new staff accounts at /en/settings/staff/add/."""

    STAFF_ADD_URL = "/en/settings/staff/add/"

    def test_superadmin_can_create_staff_with_permissions(self, superadmin_client):
        """Superadmin can create a new staff account with granular permissions."""
        assert hasattr(
            User, "can_delete_records"
        ), "User model must have 'can_delete_records' field."
        assert hasattr(User, "can_manage_shop"), "User model must have 'can_manage_shop' field."
        assert hasattr(
            User, "can_manage_categories"
        ), "User model must have 'can_manage_categories' field."

        post_data = {
            "username": "new_clerk",
            "email": "clerk@example.com",
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
            "first_name": "New",
            "last_name": "Clerk",
            "can_delete_records": "on",
            "can_manage_shop": "on",
            # can_manage_categories omitted -> should be False
        }
        response = superadmin_client.post(self.STAFF_ADD_URL, post_data)
        assert response.status_code in [200, 302]

        created = User.objects.filter(username="new_clerk").first()
        assert created is not None, "New staff user was not created in database."
        assert created.role == User.Role.STAFF
        assert created.check_password("SecurePassword123!") is True
        assert created.can_delete_records is True
        assert created.can_manage_shop is True
        assert created.can_manage_categories is False
        assert created.is_active is True

    def test_superadmin_can_create_staff_with_urdu_or_unicode_name(self, superadmin_client):
        """Staff members with Urdu/Unicode first and last names are stored cleanly."""
        post_data = {
            "username": "ahmed_urdu",
            "email": "ahmed@example.com",
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
            "first_name": "احمد",
            "last_name": "خان",
        }
        response = superadmin_client.post(self.STAFF_ADD_URL, post_data)
        assert response.status_code in [200, 302]

        user = User.objects.filter(username="ahmed_urdu").first()
        assert user is not None
        assert user.first_name == "احمد"
        assert user.last_name == "خان"

    def test_create_staff_duplicate_username_fails(self, superadmin_client, target_staff):
        """Attempting to create a user with an existing username is rejected."""
        post_data = {
            "username": target_staff.username,  # already exists
            "email": "another@example.com",
            "password": "Password123!",
            "password_confirm": "Password123!",
        }
        response = superadmin_client.post(self.STAFF_ADD_URL, post_data)
        assert response.status_code in [200, 400]
        # Should not raise 500 and count remains 1 for that username
        assert User.objects.filter(username=target_staff.username).count() == 1

    def test_create_staff_password_mismatch_fails(self, superadmin_client):
        """Mismatched passwords reject staff creation."""
        post_data = {
            "username": "mismatch_user",
            "email": "mismatch@example.com",
            "password": "Password123!",
            "password_confirm": "DifferentPassword456!",
        }
        response = superadmin_client.post(self.STAFF_ADD_URL, post_data)
        assert response.status_code in [200, 400]
        assert not User.objects.filter(username="mismatch_user").exists()

    def test_create_staff_empty_username_or_password_fails(self, superadmin_client):
        """Empty username or password fails form validation."""
        post_data = {
            "username": "",
            "email": "empty@example.com",
            "password": "",
            "password_confirm": "",
        }
        response = superadmin_client.post(self.STAFF_ADD_URL, post_data)
        assert response.status_code in [200, 400]

    def test_non_superadmin_cannot_create_staff(self, staff_client):
        """Staff users cannot create new staff accounts (HTTP 403 or redirect)."""
        post_data = {
            "username": "rogue_staff",
            "email": "rogue@example.com",
            "password": "Password123!",
            "password_confirm": "Password123!",
        }
        response = staff_client.post(self.STAFF_ADD_URL, post_data)
        assert response.status_code in [403, 302]
        assert not User.objects.filter(username="rogue_staff").exists()


@pytest.mark.django_db
class TestStaffToggleStatus:
    """Tests for enabling/disabling staff accounts at /en/settings/staff/<id>/toggle-status/."""

    def test_superadmin_can_deactivate_active_staff(self, superadmin_client, target_staff):
        """Superadmin can toggle an active staff member to inactive (disabled)."""
        assert target_staff.is_active is True
        url = f"/en/settings/staff/{target_staff.pk}/toggle-status/"

        response = superadmin_client.post(url)
        assert response.status_code in [200, 302]

        target_staff.refresh_from_db()
        assert target_staff.is_active is False

    def test_deactivated_staff_cannot_login(self, client, target_staff):
        """Deactivated staff user cannot authenticate into the system."""
        target_staff.is_active = False
        target_staff.save()

        login_url = reverse("accounts:login")
        response = client.post(
            login_url,
            {"username": target_staff.username, "password": "InitialStaffPass123!"},
        )
        # Should not log in
        assert client.session.get("_auth_user_id") is None
        assert response.status_code in [200, 302]

    def test_superadmin_can_reactivate_deactivated_staff(self, superadmin_client, target_staff):
        """Superadmin can toggle an inactive staff member back to active."""
        target_staff.is_active = False
        target_staff.save()

        url = f"/en/settings/staff/{target_staff.pk}/toggle-status/"
        response = superadmin_client.post(url)
        assert response.status_code in [200, 302]

        target_staff.refresh_from_db()
        assert target_staff.is_active is True

    def test_superadmin_cannot_disable_self(self, superadmin_client, superadmin_user):
        """Superadmin cannot disable their own account (prevents self-lockout)."""
        # Ensure staff endpoint is implemented first
        list_resp = superadmin_client.get("/en/settings/staff/")
        assert list_resp.status_code == 200, "Staff management endpoints not implemented"

        url = f"/en/settings/staff/{superadmin_user.pk}/toggle-status/"
        response = superadmin_client.post(url)
        # Should be rejected or gracefully ignore self-deactivation
        assert response.status_code in [200, 302, 400]

        superadmin_user.refresh_from_db()
        assert superadmin_user.is_active is True

    def test_toggle_nonexistent_staff_returns_404(self, superadmin_client):
        """Toggling status of a non-existent user ID returns HTTP 404."""
        # Ensure staff management is mounted
        list_resp = superadmin_client.get("/en/settings/staff/")
        assert list_resp.status_code == 200, "Staff management endpoints not implemented"

        url = "/en/settings/staff/999999/toggle-status/"
        response = superadmin_client.post(url)
        assert response.status_code == 404

    def test_non_superadmin_cannot_toggle_status(self, staff_client, target_staff):
        """Staff user cannot toggle the active status of accounts."""
        url = f"/en/settings/staff/{target_staff.pk}/toggle-status/"
        response = staff_client.post(url)
        assert response.status_code in [403, 302]

        target_staff.refresh_from_db()
        assert target_staff.is_active is True


@pytest.mark.django_db
class TestStaffPermissionsUpdate:
    """Tests for updating staff permissions at /en/settings/staff/<id>/permissions/."""

    def test_superadmin_can_update_staff_permissions(self, superadmin_client, target_staff):
        """Superadmin can grant permission checkboxes to a staff member."""
        assert hasattr(User, "can_delete_records"), "User model must define 'can_delete_records'."
        assert hasattr(User, "can_manage_shop"), "User model must define 'can_manage_shop'."
        assert hasattr(
            User, "can_manage_categories"
        ), "User model must define 'can_manage_categories'."

        url = f"/en/settings/staff/{target_staff.pk}/permissions/"
        post_data = {
            "can_delete_records": "on",
            "can_manage_shop": "on",
            # can_manage_categories omitted (False)
        }
        response = superadmin_client.post(url, post_data)
        assert response.status_code in [200, 302]

        target_staff.refresh_from_db()
        assert target_staff.can_delete_records is True
        assert target_staff.can_manage_shop is True
        assert target_staff.can_manage_categories is False

    def test_superadmin_can_revoke_all_permissions(self, superadmin_client, target_staff):
        """Superadmin can revoke all permissions by clearing all checkboxes."""
        if hasattr(target_staff, "can_manage_shop"):
            target_staff.can_manage_shop = True
            target_staff.can_delete_records = True
            target_staff.save()

        url = f"/en/settings/staff/{target_staff.pk}/permissions/"
        response = superadmin_client.post(url, {})  # all unchecked
        assert response.status_code in [200, 302]

        target_staff.refresh_from_db()
        if hasattr(target_staff, "can_manage_shop"):
            assert target_staff.can_manage_shop is False
            assert target_staff.can_delete_records is False
            assert target_staff.can_manage_categories is False

    def test_update_permissions_nonexistent_staff_returns_404(self, superadmin_client):
        """Updating permissions for non-existent user returns HTTP 404."""
        # Ensure staff management is mounted
        list_resp = superadmin_client.get("/en/settings/staff/")
        assert list_resp.status_code == 200, "Staff management endpoints not implemented"

        url = "/en/settings/staff/999999/permissions/"
        response = superadmin_client.post(url, {"can_manage_shop": "on"})
        assert response.status_code == 404

    def test_non_superadmin_cannot_update_permissions(self, staff_client, target_staff):
        """Staff user cannot update permission checkboxes."""
        url = f"/en/settings/staff/{target_staff.pk}/permissions/"
        response = staff_client.post(url, {"can_manage_shop": "on"})
        assert response.status_code in [403, 302]


@pytest.mark.django_db
class TestStaffPasswordReset:
    """Tests for resetting staff passwords at /en/settings/staff/<id>/reset-password/."""

    def test_superadmin_can_reset_staff_password(self, superadmin_client, target_staff):
        """Superadmin can set a new password for a staff member."""
        url = f"/en/settings/staff/{target_staff.pk}/reset-password/"
        post_data = {
            "new_password": "NewStaffPassword456!",
            "new_password_confirm": "NewStaffPassword456!",
        }
        response = superadmin_client.post(url, post_data)
        assert response.status_code in [200, 302]

        target_staff.refresh_from_db()
        assert target_staff.check_password("NewStaffPassword456!") is True

    def test_password_reset_clears_lockout_and_failed_attempts(
        self, superadmin_client, locked_staff
    ):
        """Resetting a locked staff member's password clears lockout state."""
        assert locked_staff.is_locked is True
        assert locked_staff.failed_login_attempts == 5

        url = f"/en/settings/staff/{locked_staff.pk}/reset-password/"
        post_data = {
            "new_password": "FreshPassword789!",
            "new_password_confirm": "FreshPassword789!",
        }
        response = superadmin_client.post(url, post_data)
        assert response.status_code in [200, 302]

        locked_staff.refresh_from_db()
        assert locked_staff.check_password("FreshPassword789!") is True
        assert locked_staff.is_locked is False
        assert locked_staff.failed_login_attempts == 0
        assert locked_staff.locked_until is None

    def test_reset_password_mismatch_rejected(self, superadmin_client, target_staff):
        """Mismatched new password and confirmation rejects the update."""
        url = f"/en/settings/staff/{target_staff.pk}/reset-password/"
        post_data = {
            "new_password": "NewStaffPassword456!",
            "new_password_confirm": "MismatchPassword999!",
        }
        response = superadmin_client.post(url, post_data)
        assert response.status_code in [200, 400]

        target_staff.refresh_from_db()
        assert target_staff.check_password("InitialStaffPass123!") is True

    def test_reset_password_nonexistent_staff_returns_404(self, superadmin_client):
        """Resetting password for a non-existent user ID returns HTTP 404."""
        # Ensure staff management is mounted
        list_resp = superadmin_client.get("/en/settings/staff/")
        assert list_resp.status_code == 200, "Staff management endpoints not implemented"

        url = "/en/settings/staff/999999/reset-password/"
        response = superadmin_client.post(
            url,
            {"new_password": "Pass!", "new_password_confirm": "Pass!"},
        )
        assert response.status_code == 404

    def test_non_superadmin_cannot_reset_passwords(self, staff_client, target_staff):
        """Staff members cannot reset passwords for any user."""
        url = f"/en/settings/staff/{target_staff.pk}/reset-password/"
        response = staff_client.post(
            url,
            {"new_password": "Hack!", "new_password_confirm": "Hack!"},
        )
        assert response.status_code in [403, 302]

        target_staff.refresh_from_db()
        assert target_staff.check_password("InitialStaffPass123!") is True
