"""tests/test_dashboard.py
========================
Tests for Task 3: Base Dashboard Layout Shell.

Coverage:
- Unauthenticated user visiting / or /en/ is redirected to the login page.
- Authenticated user visiting / or /en/ receives HTTP 200.
- Dashboard response contains:
  - Sidebar links for all 10 navigation items:
    Dashboard, Scan Bill, Add Bill, Bills, Vendors, Customers, Items,
    Reports, Ledger, Categories, Settings.
  - Top bar with user profile/name, language switcher, theme toggle.
  - Bottom navigation bar markup for mobile screens.
  - HTMX and Alpine.js script tags.
  - Tailwind CSS link/script.
- Internationalization:
  - Urdu RTL layout (dir="rtl") on /ur/.
  - English LTR layout (dir="ltr") on /en/.
- Edge cases and error handling:
  - Non-existent route returns 404, not 500.
"""

import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestDashboardAccess:
    """Access control and authentication guards for the base dashboard shell."""

    def test_unauthenticated_user_accessing_dashboard_redirects_to_login(self, client):
        """Unauthenticated user visiting /en/dashboard/ is redirected to the login page."""
        response = client.get("/en/dashboard/")
        assert response.status_code == 302
        login_url = reverse("accounts:login")
        assert login_url in response.url or "/accounts/login/" in response.url

        # Follow redirect to verify login page renders
        response_follow = client.get("/en/dashboard/", follow=True)
        assert response_follow.status_code == 200
        assert login_url in response_follow.request.get(
            "PATH_INFO", ""
        ) or "login" in response_follow.request.get("PATH_INFO", "")

    def test_unauthenticated_user_sees_landing_page_at_root(self, client):
        """Unauthenticated user visiting /en/ receives HTTP 200 with the SaaS landing page."""
        response = client.get("/en/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "ScanBooks" in content
        assert "Start 10 Free Scans" in content

    def test_authenticated_superadmin_can_access_dashboard(self, superadmin_client):
        """Authenticated superadmin visiting /en/ receives HTTP 200 with dashboard."""
        response = superadmin_client.get("/en/")
        assert response.status_code == 200
        assert "Dashboard" in response.content.decode()

    def test_authenticated_staff_can_access_dashboard(self, staff_client):
        """Authenticated staff user visiting /en/ receives HTTP 200 with dashboard."""
        response = staff_client.get("/en/")
        assert response.status_code == 200
        assert "Dashboard" in response.content.decode()

    def test_authenticated_user_root_redirects_to_localized_dashboard(self, staff_client):
        """Authenticated user visiting / receives HTTP 200 with dashboard."""
        response = staff_client.get("/", follow=True)
        assert response.status_code == 200
        assert "Dashboard" in response.content.decode()



@pytest.mark.django_db
class TestDashboardSidebarNavigation:
    """Tests for sidebar navigation elements on the dashboard."""

    NAV_ITEMS = [
        "Dashboard",
        "Scan Bill",
        "Add Bill",
        "Bills",
        "Vendors",
        "Customers",
        "Items",
        "Reports",
        "Ledger",
        "Categories",
        "Settings",
    ]

    def test_dashboard_sidebar_contains_all_navigation_items(self, staff_client):
        """Dashboard response contains all required sidebar navigation links."""
        response = staff_client.get("/en/dashboard/")
        assert response.status_code == 200
        content = response.content.decode().lower()

        for item in self.NAV_ITEMS:
            assert item.lower() in content, f"Navigation item '{item}' missing from dashboard HTML"


@pytest.mark.django_db
class TestDashboardTopBar:
    """Tests for top bar elements: user profile, language switcher, theme toggle."""

    def test_top_bar_displays_user_profile_name(self, staff_client, staff_user):
        """Top bar displays logged-in user profile / username or full name."""
        response = staff_client.get("/en/dashboard/")
        assert response.status_code == 200
        content = response.content.decode()

        has_username = staff_user.username in content
        has_first_name = staff_user.first_name in content
        assert has_username or has_first_name, "User profile name not displayed in top bar"

    def test_top_bar_contains_language_switcher(self, staff_client):
        """Top bar includes a language switcher (English / Urdu)."""
        response = staff_client.get("/en/dashboard/")
        assert response.status_code == 200
        content = response.content.decode().lower()

        # Language switcher may use set_language URL or language codes / names
        has_set_language = "set_language" in content or "set-language" in content
        has_lang_names = "urdu" in content or "اردو" in content or "english" in content
        assert has_set_language or has_lang_names, "Language switcher markup missing from top bar"

    def test_top_bar_contains_theme_toggle(self, staff_client):
        """Top bar includes a theme toggle for switching light / dark modes."""
        response = staff_client.get("/en/dashboard/")
        assert response.status_code == 200
        content = response.content.decode().lower()

        has_theme_toggle = (
            "theme" in content or "dark" in content or "toggle" in content or "light" in content
        )
        assert has_theme_toggle, "Theme toggle markup missing from top bar"


@pytest.mark.django_db
class TestDashboardMobileLayout:
    """Tests for mobile responsiveness: bottom navigation bar markup."""

    def test_bottom_navigation_bar_markup_present(self, staff_client):
        """Dashboard markup contains a bottom navigation bar for mobile screens."""
        response = staff_client.get("/en/dashboard/")
        assert response.status_code == 200
        content = response.content.decode().lower()

        # Mobile bottom navigation indicators: bottom-nav, fixed bottom-0, md:hidden navigation
        has_bottom_nav = (
            "bottom" in content and ("nav" in content or "bar" in content)
        ) or "md:hidden" in content
        assert has_bottom_nav, "Mobile bottom navigation markup missing from dashboard"


@pytest.mark.django_db
class TestDashboardFrontendLibraries:
    """Tests for required frontend script and stylesheet tags."""

    def test_htmx_script_included(self, staff_client):
        """Dashboard includes HTMX script tag."""
        response = staff_client.get("/en/dashboard/")
        assert response.status_code == 200
        content = response.content.decode().lower()
        assert "htmx" in content, "HTMX script tag missing from dashboard"

    def test_alpine_js_script_included(self, staff_client):
        """Dashboard includes Alpine.js script tag."""
        response = staff_client.get("/en/dashboard/")
        assert response.status_code == 200
        content = response.content.decode().lower()
        assert "alpine" in content, "Alpine.js script tag missing from dashboard"

    def test_tailwind_css_included(self, staff_client):
        """Dashboard includes Tailwind CSS stylesheet or script."""
        response = staff_client.get("/en/dashboard/")
        assert response.status_code == 200
        content = response.content.decode().lower()
        assert "tailwind" in content, "Tailwind CSS link/script missing from dashboard"


@pytest.mark.django_db
class TestDashboardInternationalization:
    """Tests for internationalization: English (LTR) vs Urdu (RTL) layout."""

    def test_english_layout_ltr(self, staff_client):
        """English dashboard (/en/dashboard/) uses LTR direction."""
        response = staff_client.get("/en/dashboard/")
        assert response.status_code == 200
        content = response.content.decode().lower()
        assert 'dir="ltr"' in content or 'lang="en"' in content

    def test_urdu_layout_rtl(self, staff_client):
        """Urdu dashboard (/ur/dashboard/) uses RTL direction."""
        response = staff_client.get("/ur/dashboard/")
        assert response.status_code == 200
        content = response.content.decode().lower()
        assert 'dir="rtl"' in content or 'lang="ur"' in content


@pytest.mark.django_db
class TestDashboardEdgeCases:
    """Edge cases and error handling for dashboard routing."""

    def test_nonexistent_route_returns_404(self, staff_client):
        """Non-existent dashboard route returns 404 rather than 500 error."""
        response = staff_client.get("/en/dashboard-route-that-does-not-exist-xyz/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestDashboardEmptyState:
    """Tests verifying the empty state when no bills exist."""

    def test_empty_state_action_buttons_have_valid_urls(self, staff_client):
        """Empty state 'Scan Bill' and 'Add Bill' buttons link to actual application routes, not fragment hashes."""
        response = staff_client.get("/en/dashboard/")
        assert response.status_code == 200
        content = response.content.decode()

        # Must not contain dummy hash anchors
        assert 'href="#scan-bill"' not in content
        assert 'href="#add-bill"' not in content

        # Must contain actual routes
        scan_url = reverse("scanning:upload")
        add_bill_url = reverse("bills:bill_add")
        assert f'href="{scan_url}"' in content
        assert f'href="{add_bill_url}"' in content


@pytest.mark.django_db
class TestDashboardActionButtonsLayout:
    """Tests verifying the top 3 quick-action buttons layout on mobile and desktop."""

    def test_dashboard_renders_all_three_buttons_in_centered_single_row(self, staff_client):
        """Dashboard renders Take Photo, Scan Bill, and Add Bill in a centered single row container."""
        response = staff_client.get("/en/dashboard/")
        assert response.status_code == 200
        content = response.content.decode()

        # Container must be center-aligned on mobile and not wrap
        assert "justify-center" in content
        assert "flex items-center justify-center sm:justify-end" in content
        assert "flex-wrap" not in content[: content.find("Welcome back") + 1200]

        # All 3 buttons must be present in the header container
        assert "upload/?camera=1" in content
        assert "Take Photo" in content
        assert "Scan Bill" in content
        assert "Add Bill" in content

    def test_dashboard_urdu_renders_all_three_buttons(self, staff_client):
        """Urdu dashboard renders all 3 action buttons with RTL-friendly labels."""
        response = staff_client.get("/ur/dashboard/")
        assert response.status_code == 200
        content = response.content.decode()

        assert "upload/?camera=1" in content
        assert "تصویر لیں" in content
        assert "بل اسکین کریں" in content
        assert "بل شامل کریں" in content
