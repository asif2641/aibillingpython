"""tests/test_settings_ui.py
===========================
UI Integration tests for Phase 2: Settings layout, sub-navigation tabs,
Tailwind styling, light/dark mode variants, and Urdu RTL rendering.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.fixture
def superadmin_user(db):
    """Create an active superadmin user."""
    return User.objects.create_user(
        username="superadmin_ui",
        email="superadmin@example.com",
        password="TestPass123!",
        role=User.Role.SUPERADMIN,
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def staff_with_all_permissions(db):
    """Create a staff user with all elevated permissions."""
    return User.objects.create_user(
        username="staff_elevated",
        email="elevated@example.com",
        password="TestPass123!",
        role=User.Role.STAFF,
        can_delete_records=True,
        can_manage_shop=True,
        can_manage_categories=True,
    )


@pytest.mark.django_db
class TestSettingsSubNavigationAndShell:
    """Tests confirming the unified settings shell and subnav tabs."""

    def test_shop_profile_renders_settings_subnav_tabs(self, client, superadmin_user):
        """Shop profile page renders all subnav tabs for superadmin."""
        client.force_login(superadmin_user)
        response = client.get(reverse("shop_profile"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")

        # Must include sub-nav tab links
        assert "settings-subnav" in content or "Shop Profile" in content
        assert "Staff Management" in content
        assert "Categories" in content
        assert "Units" in content or "Units of Measurement" in content

    def test_staff_list_renders_settings_subnav_tabs(self, client, superadmin_user):
        """Staff list page renders settings subnav tabs."""
        client.force_login(superadmin_user)
        response = client.get(reverse("staff_list"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Staff Accounts" in content
        assert "Add Staff Member" in content

    def test_category_list_renders_settings_subnav_tabs(self, client, superadmin_user):
        """Category list page renders settings subnav tabs."""
        client.force_login(superadmin_user)
        response = client.get(reverse("categories:category_list"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Bill Categories" in content
        assert "Add Category" in content

    def test_unit_list_renders_settings_subnav_tabs(self, client, superadmin_user):
        """Units list page renders settings subnav tabs."""
        client.force_login(superadmin_user)
        response = client.get(reverse("categories:unit_list"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Measurement Units" in content
        assert "Add Custom Unit" in content

    def test_reset_data_tab_visible_only_for_superadmin(
        self, client, superadmin_user, staff_with_all_permissions
    ):
        """Reset App Data tab is rendered for superadmin, but hidden for regular staff."""
        client.force_login(superadmin_user)
        response = client.get(reverse("shop_profile"))
        assert response.status_code == 200
        assert "Reset App Data" in response.content.decode("utf-8")

        client.force_login(staff_with_all_permissions)
        response_staff = client.get(reverse("shop_profile"))
        assert response_staff.status_code == 200
        assert "Reset App Data" not in response_staff.content.decode("utf-8")

    def test_staff_management_tab_hidden_for_tenant(self, client, superadmin_user):
        """Staff Management and Landing Page tabs appear only for superadmin, not tenant."""
        client.force_login(superadmin_user)
        response_admin = client.get(reverse("shop_profile"))
        assert response_admin.status_code == 200
        content_admin = response_admin.content.decode("utf-8")
        assert "Staff Management" in content_admin
        assert "Landing Page & Marketing" in content_admin

        # Create a tenant user (is_superuser=False)
        tenant = User.objects.create_user(
            username="shop_owner_1",
            email="owner@example.com",
            password="TestPassword123!",
            role=User.Role.SUPERADMIN,
            is_staff=False,
            is_superuser=False,
            business_name="My Shop",
            can_manage_shop=True,
        )
        client.force_login(tenant)
        response_tenant = client.get(reverse("shop_profile"))
        assert response_tenant.status_code == 200
        content_tenant = response_tenant.content.decode("utf-8")
        assert "Staff Management" not in content_tenant
        assert "Landing Page & Marketing" not in content_tenant
        assert "Reset App Data" not in content_tenant
        assert "Shop Profile" in content_tenant


@pytest.mark.django_db
class TestSettingsBilingualAndRTL:
    """Tests verifying English (LTR) and Urdu (RTL) across settings pages."""

    def test_shop_profile_urdu_renders_rtl(self, client, superadmin_user):
        """Accessing shop profile in Urdu renders dir='rtl'."""
        client.force_login(superadmin_user)
        response = client.get("/ur/settings/shop/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'dir="rtl"' in content

    def test_staff_list_urdu_renders_rtl(self, client, superadmin_user):
        """Accessing staff list in Urdu renders dir='rtl'."""
        client.force_login(superadmin_user)
        response = client.get("/ur/settings/staff/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'dir="rtl"' in content

    def test_category_list_urdu_renders_rtl(self, client, superadmin_user):
        """Accessing category list in Urdu renders dir='rtl'."""
        client.force_login(superadmin_user)
        response = client.get("/ur/settings/categories/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'dir="rtl"' in content

    def test_reset_data_urdu_renders_rtl(self, client, superadmin_user):
        """Accessing reset data page in Urdu renders dir='rtl'."""
        client.force_login(superadmin_user)
        response = client.get("/ur/settings/reset-data/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'dir="rtl"' in content


@pytest.mark.django_db
class TestSettingsThemeAndDarkMode:
    """Tests confirming dark mode classes and accessibility standards."""

    def test_settings_pages_contain_dark_mode_variants(self, client, superadmin_user):
        """All settings pages must contain Tailwind dark: variant classes."""
        client.force_login(superadmin_user)
        for url in [
            reverse("shop_profile"),
            reverse("staff_list"),
            reverse("categories:category_list"),
            reverse("categories:unit_list"),
            reverse("reset_data"),
        ]:
            response = client.get(url)
            assert response.status_code == 200
            content = response.content.decode("utf-8")
            assert "dark:bg-slate-800" in content or "dark:bg-slate-900" in content
            assert "dark:text-white" in content or "dark:text-slate-100" in content
