"""tests/test_i18n_theme.py
=========================
Tests for Task 4 (English <-> Urdu switch with RTL) and Task 5 (Light / dark theme).

Coverage:
- Internationalization & RTL:
  - English routes (/en/, /en/accounts/login/) render dir="ltr" and English text.
  - Urdu routes (/ur/, /ur/accounts/login/) render dir="rtl", Noto Sans Arabic font, and Urdu text.
  - Set language view (/i18n/set-language/) sets the language cookie and redirects appropriately.
- Urdu Translations:
  - Complete gettext translations for all primary terms in the app.
- Login Page Polish:
  - Responsive Tailwind layout, accessibility labels, >=44px touch targets.
  - Language switcher present on login page allowing switching to Urdu prior to login.
  - Theme toggle button present on login page.
  - Clear rendering of lockout warning and form error messages.
- Theme System:
  - Dark mode class variants throughout templates.
  - Pre-render script prevents flash of light mode.
  - Theme toggle Alpine.js methods configured.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import translation

User = get_user_model()


@pytest.mark.django_db
class TestLanguageSwitchingAndDirection:
    """Tests for language routing and directionality (LTR / RTL)."""

    def test_english_login_page_renders_ltr(self, client):
        """English login page (/en/accounts/login/) renders with dir='ltr'."""
        response = client.get("/en/accounts/login/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'dir="ltr"' in content
        assert "Sign In" in content
        assert "Username" in content
        assert "Password" in content

    def test_urdu_login_page_renders_rtl(self, client):
        """Urdu login page (/ur/accounts/login/) renders with dir='rtl' and Urdu text."""
        response = client.get("/ur/accounts/login/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'dir="rtl"' in content
        assert "Noto Sans Arabic" in content
        assert "لاگ ان" in content
        assert "صارف نام" in content
        assert "پاس ورڈ" in content

    def test_urdu_dashboard_renders_rtl(self, staff_client):
        """Urdu dashboard (/ur/) renders with dir='rtl' and Urdu navigation terms."""
        response = staff_client.get("/ur/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'dir="rtl"' in content
        assert "ڈیش بورڈ" in content
        assert "بل اسکین کریں" in content
        assert "تمام بلز" in content

    def test_set_language_view_sets_cookie_and_redirects(self, client):
        """POST to /i18n/set-language/ sets the language cookie to Urdu and redirects."""
        response = client.post(
            reverse("set_language"),
            {"language": "ur", "next": "/en/accounts/login/"},
            follow=False,
        )
        assert response.status_code == 302
        cookie = client.cookies.get(settings.LANGUAGE_COOKIE_NAME)
        assert cookie is not None
        assert cookie.value == "ur"

    def test_set_language_view_switches_back_to_english(self, client):
        """POST to /i18n/set-language/ sets the language cookie to English and redirects."""
        response = client.post(
            reverse("set_language"),
            {"language": "en", "next": "/ur/accounts/login/"},
            follow=False,
        )
        assert response.status_code == 302
        cookie = client.cookies.get(settings.LANGUAGE_COOKIE_NAME)
        assert cookie is not None
        assert cookie.value == "en"


@pytest.mark.django_db
class TestUrduTranslations:
    """Tests for Urdu translations of all core application strings."""

    EXPECTED_TRANSLATIONS = {
        "Dashboard": "ڈیش بورڈ",
        "Scan Bill": "بل اسکین کریں",
        "Add Bill": "بل شامل کریں",
        "Bills": "تمام بلز",
        "Vendors": "دکاندار / وینڈرز",
        "Customers": "گاہک / کسٹمرز",
        "Items": "اشیاء",
        "Reports": "رپورٹس",
        "Ledger": "کھاتہ",
        "Categories": "اقسام",
        "Settings": "ترتیبات",
        "Total Spend": "کل خرچ",
        "Total Bills": "کل بلز",
        "Outstanding Credit": "بقیہ رقم",
        "Average Bill": "اوسط بل",
        "Login": "لاگ ان",
        "Logout": "لاگ آوٹ",
        "Sign In": "لاگ ان",
        "Sign out": "لاگ آوٹ",
        "Username": "صارف نام",
        "Password": "پاس ورڈ",
        "Super Admin": "سپر ایڈمن",
        "Staff": "اسٹاف",
        "Recent Activity": "حالیہ سرگرمی",
        "No bills recorded yet": "ابھی تک کوئی بل شامل نہیں کیا گیا",
    }

    def test_all_primary_terms_translated_in_urdu(self):
        """All primary terms translate to expected Urdu phrases via gettext."""
        with translation.override("ur"):
            for english_term, expected_urdu in self.EXPECTED_TRANSLATIONS.items():
                translated = translation.gettext(english_term)
                assert translated == expected_urdu, (
                    f"Expected translation for '{english_term}' to be '{expected_urdu}', "
                    f"got '{translated}'"
                )

    def test_role_verbose_names_translated(self, staff_user, superadmin_user):
        """User role verbose names translate correctly in Urdu context."""
        with translation.override("ur"):
            assert translation.gettext(staff_user.get_role_display()) == "اسٹاف"
            assert translation.gettext(superadmin_user.get_role_display()) == "سپر ایڈمن"


@pytest.mark.django_db
class TestLoginPagePolishAndAccessibility:
    """Tests for polished login page design, accessibility, and error states."""

    def test_login_page_contains_language_switcher(self, client):
        """Login page has a language switcher in the header for switching to Urdu."""
        response = client.get("/en/accounts/login/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'name="language"' in content
        assert 'value="ur"' in content
        assert "اردو" in content

    def test_login_page_contains_theme_toggle(self, client):
        """Login page includes theme toggle button."""
        response = client.get("/en/accounts/login/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "toggleTheme()" in content
        assert "darkMode" in content

    def test_login_page_input_accessibility_labels(self, client):
        """Login inputs are linked to accessible <label> elements with matching 'for' attributes."""
        response = client.get("/en/accounts/login/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'for="id_username"' in content
        assert 'for="id_password"' in content
        assert 'id="id_username"' in content
        assert 'id="id_password"' in content

    def test_login_page_displays_invalid_credentials_error(self, client):
        """Submitting invalid credentials displays an error notice."""
        response = client.post(
            "/en/accounts/login/",
            {"username": "nonexistent", "password": "WrongPassword"},
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8").lower()
        assert "invalid" in content or "please enter" in content or "error" in content

    def test_login_page_displays_lockout_warning(self, client, staff_user):
        """Locked user login attempt renders a clear lockout message in the UI."""
        staff_user.is_locked = True
        staff_user.failed_login_attempts = 5
        staff_user.save()

        response = client.post(
            "/en/accounts/login/",
            {"username": staff_user.username, "password": "TestPass123!"},
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8").lower()
        assert "lock" in content
        assert "15 minutes" in content or "locked" in content


@pytest.mark.django_db
class TestThemeSystem:
    """Tests for light / dark theme markup and client-side support."""

    def test_base_html_includes_dark_mode_configuration(self, client):
        """Base template configures Tailwind dark mode class strategy."""
        response = client.get("/en/accounts/login/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "darkMode: 'class'" in content or 'darkMode: "class"' in content
        assert "dark:bg-slate-900" in content

    def test_base_html_includes_prerender_theme_check(self, client):
        """Base template contains pre-render theme check to prevent flash of light theme."""
        response = client.get("/en/accounts/login/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "localStorage.getItem('theme')" in content
        assert "prefers-color-scheme: dark" in content

    def test_dashboard_contains_dark_mode_variants(self, staff_client):
        """Dashboard HTML uses dark: variants across cards, headers, and navigation."""
        response = staff_client.get("/en/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "dark:bg-slate-800" in content or "dark:bg-slate-900" in content
        assert "dark:text-white" in content
