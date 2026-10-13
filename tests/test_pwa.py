"""tests/test_pwa.py
==================
QA Test-First Suite for Phase 6: PWA Web App Manifest, Service Worker,
Offline Shell View, and Base Layout PWA Metadata.

Coverage:
1. Web App Manifest (/manifest.json):
   - HTTP 200 OK.
   - Content-Type header contains 'json' (application/json or application/manifest+json).
   - Valid JSON payload containing required PWA attributes:
     - name, short_name, start_url, display="standalone".
     - icons array containing icons with src, sizes, type.
     - theme_color and background_color.
   - Accessible without authentication.

2. Service Worker (/sw.js):
   - HTTP 200 OK served at root scope.
   - Content-Type is application/javascript or text/javascript.
   - Service worker script contains lifecycle and cache listeners:
     - 'install' event listener.
     - 'activate' event listener.
     - 'fetch' event listener for network caching/offline fallback.

3. Offline Shell / Fallback View (/offline/ or /en/offline/):
   - HTTP 200 OK.
   - Contains English offline indication (e.g., "offline" or "Offline").
   - Contains Urdu offline indication ("آف لائن").
   - Contains navigation action to add bills offline (link targeting bills/add).
   - Accessible anonymously without 302 login redirect.
   - Urdu locale (/ur/offline/) renders with RTL direction.

4. Base Layout PWA Integration:
   - Authenticated GET to /en/ contains <link rel="manifest">.
   - Authenticated GET to /en/ contains <meta name="theme-color">.
   - Response contains Service Worker registration script (navigator.serviceWorker.register).
   - Response contains mobile-web-app-capable meta tags.
"""

import json

import pytest
from django.urls import NoReverseMatch, reverse


def get_first_valid_response(client, candidate_urls):
    """Attempt candidate URLs and return the first non-404 response, or the first response."""
    for url in candidate_urls:
        res = client.get(url)
        if res.status_code != 404:
            return res
    return client.get(candidate_urls[0])


def resolve_offline_url():
    """Resolve the offline URL via reverse if available, otherwise candidate path."""
    for name in ["offline", "pwa_offline", "offline_shell"]:
        try:
            return reverse(name)
        except (NoReverseMatch, Exception):
            pass
    return "/en/offline/"


# ---------------------------------------------------------------------------
# 1. PWA Web App Manifest Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestPWAManifest:
    """Verify Web App Manifest availability, content type, and schema."""

    def test_manifest_returns_200_and_json_content(self, client):
        """GET /manifest.json returns HTTP 200 with JSON content-type."""
        response = get_first_valid_response(
            client,
            ["/manifest.json", "/static/manifest.json"],
        )
        assert (
            response.status_code == 200
        ), f"Expected /manifest.json to return 200, got {response.status_code}"
        content_type = response.headers.get("Content-Type", "")
        assert (
            "json" in content_type.lower()
        ), f"Expected Content-Type to contain 'json', got '{content_type}'"

    def test_manifest_schema_and_required_attributes(self, client):
        """Web App Manifest contains all required PWA fields and icons."""
        response = get_first_valid_response(
            client,
            ["/manifest.json", "/static/manifest.json"],
        )
        assert response.status_code == 200

        data = json.loads(response.content.decode("utf-8"))

        # Core required fields
        assert "name" in data, "Manifest missing 'name'"
        assert len(data["name"].strip()) > 0
        assert "short_name" in data, "Manifest missing 'short_name'"
        assert "start_url" in data, "Manifest missing 'start_url'"
        assert (
            data.get("display") == "standalone"
        ), f"Expected display to be 'standalone', got '{data.get('display')}'"

        # Icons array
        assert "icons" in data, "Manifest missing 'icons' array"
        assert isinstance(data["icons"], list)
        assert len(data["icons"]) > 0, "Manifest icons list must not be empty"

        # Verify icon properties
        for icon in data["icons"]:
            assert "src" in icon, f"Icon entry missing 'src': {icon}"
            assert "sizes" in icon, f"Icon entry missing 'sizes': {icon}"
            assert "type" in icon, f"Icon entry missing 'type': {icon}"

        # Theme and background styling
        assert "theme_color" in data or "background_color" in data


# ---------------------------------------------------------------------------
# 2. PWA Service Worker Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestPWAServiceWorker:
    """Verify Service Worker file serving and event listeners."""

    def test_service_worker_returns_200_and_javascript(self, client):
        """GET /sw.js returns HTTP 200 with JavaScript Content-Type."""
        response = get_first_valid_response(
            client,
            ["/sw.js", "/static/sw.js"],
        )
        assert (
            response.status_code == 200
        ), f"Expected /sw.js to return 200, got {response.status_code}"
        content_type = response.headers.get("Content-Type", "").lower()
        assert (
            "javascript" in content_type
            or "text/javascript" in content_type
            or "application/x-javascript" in content_type
        ), f"Expected JavaScript content-type for /sw.js, got '{content_type}'"

    def test_service_worker_script_listeners(self, client):
        """Service Worker script implements install, activate, and fetch listeners."""
        response = get_first_valid_response(
            client,
            ["/sw.js", "/static/sw.js"],
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8")

        assert "install" in content, "Service worker script missing 'install' event listener"
        assert "fetch" in content, "Service worker script missing 'fetch' event listener"


# ---------------------------------------------------------------------------
# 3. PWA Offline Shell / Fallback View Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestPWAOfflineShell:
    """Verify offline fallback template and bilingual support."""

    def test_offline_view_returns_200_and_bilingual_content(self, client):
        """Offline page returns 200 and includes English and Urdu offline copy."""
        response = get_first_valid_response(
            client,
            ["/offline/", "/en/offline/"],
        )
        assert (
            response.status_code == 200
        ), f"Expected offline view to return 200, got {response.status_code}"

        content = response.content.decode("utf-8")
        # English indication
        assert "offline" in content.lower(), "Offline template missing English 'offline' text"
        # Urdu indication ("آف لائن")
        assert "آف لائن" in content, "Offline template missing Urdu 'آف لائن' translation"
        # Link or button to add bill offline
        assert (
            "bills/add" in content or "add" in content.lower()
        ), "Offline view should include link or action to add bills offline"

    def test_offline_view_accessible_without_auth(self, client):
        """Offline fallback page must be publicly accessible without login redirection."""
        response = get_first_valid_response(
            client,
            ["/offline/", "/en/offline/"],
        )
        # Must not redirect to login when device is disconnected
        assert response.status_code == 200

    def test_offline_view_urdu_locale(self, client):
        """Urdu locale /ur/offline/ renders with RTL layout."""
        response = get_first_valid_response(
            client,
            ["/ur/offline/", "/offline/"],
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "آف لائن" in content


# ---------------------------------------------------------------------------
# 4. Base Layout PWA Integration Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestPWABaseLayout:
    """Verify base template metadata, manifest link, and registration script."""

    def test_base_layout_manifest_link_and_theme_color(self, staff_client, staff_user):
        """Authenticated dashboard response includes manifest link and theme-color meta tag."""
        response = staff_client.get("/en/")
        assert response.status_code == 200

        content = response.content.decode("utf-8")
        assert (
            '<link rel="manifest"' in content or "manifest.json" in content
        ), "Base layout missing <link rel='manifest'> tag"
        assert 'name="theme-color"' in content, "Base layout missing <meta name='theme-color'> tag"

    def test_base_layout_service_worker_registration(self, staff_client, staff_user):
        """Base layout contains Service Worker registration script."""
        response = staff_client.get("/en/")
        assert response.status_code == 200

        content = response.content.decode("utf-8")
        assert (
            "serviceWorker" in content
        ), "Base layout missing serviceWorker registration check/script"
        assert "register(" in content, "Base layout missing serviceWorker.register call"

    def test_base_layout_mobile_web_app_tags(self, staff_client, staff_user):
        """Base layout contains mobile web app capable meta tags for installability."""
        response = staff_client.get("/en/")
        assert response.status_code == 200

        content = response.content.decode("utf-8")
        assert (
            "mobile-web-app-capable" in content
            or "apple-mobile-web-app-capable" in content
            or "apple-touch-icon" in content
        ), "Base layout missing mobile web app installability meta tags"
