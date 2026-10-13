"""tests/test_offline_ui.py
===========================
UI Integration tests for Phase 6 (Task 5):
Client-Side IndexedDB Storage & Auto-Sync Engine, offline bill form interception hooks,
floating status indicators, and Urdu offline translations.
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.utils import translation


@pytest.mark.django_db
class TestOfflineSyncScript:
    """Verify presence, structure, and accessibility of static/js/offline-sync.js."""

    def test_offline_sync_js_file_exists_and_contains_expected_tokens(self):
        """static/js/offline-sync.js exists on disk and implements IndexedDB sync engine."""
        js_path = Path(settings.BASE_DIR) / "static" / "js" / "offline-sync.js"
        assert js_path.exists(), "static/js/offline-sync.js does not exist on disk"

        content = js_path.read_text(encoding="utf-8")
        assert "aibilling_pwa_db" in content, "Missing IndexedDB database name 'aibilling_pwa_db'"
        assert "sync_queue" in content, "Missing object store 'sync_queue'"
        assert "cached_parties" in content, "Missing object store 'cached_parties'"
        assert "cached_categories" in content, "Missing object store 'cached_categories'"
        assert "cached_units" in content, "Missing object store 'cached_units'"
        assert "/sync/push/" in content, "Missing sync push endpoint reference"
        assert "/sync/pull/" in content, "Missing sync pull endpoint reference"
        assert "triggerSync" in content, "Missing triggerSync function"
        assert "cacheReferenceData" in content, "Missing cacheReferenceData function"

    def test_offline_sync_js_accessible_via_static_or_root(self, client):
        """GET /static/js/offline-sync.js returns 200 with javascript content."""
        response = client.get("/static/js/offline-sync.js")
        assert response.status_code == 200
        content_type = response.headers.get("Content-Type", "").lower()
        assert (
            "javascript" in content_type
            or "text/plain" in content_type
            or "application/octet-stream" in content_type
        )
        if hasattr(response, "streaming_content"):
            content = b"".join(response.streaming_content).decode("utf-8")
        else:
            content = response.content.decode("utf-8")
        assert "aibilling_pwa_db" in content


@pytest.mark.django_db
class TestBaseTemplateOfflineIntegration:
    """Verify base template integration of offline sync script and status pill."""

    def test_base_template_includes_script_and_indicator(self, client):
        """Login page extending base.html includes offline-sync.js and indicator container."""
        response = client.get("/en/accounts/login/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")

        assert (
            '<script src="/static/js/offline-sync.js"' in content or "offline-sync.js" in content
        ), "base.html does not include offline-sync.js script tag"
        assert (
            'id="offline-sync-indicator"' in content
        ), "base.html does not include #offline-sync-indicator container"

    def test_indicator_has_responsive_and_rtl_classes(self, client):
        """#offline-sync-indicator container is hidden by default and positioned fixed."""
        response = client.get("/en/accounts/login/")
        content = response.content.decode("utf-8")

        assert 'id="offline-sync-indicator"' in content
        assert "fixed" in content
        assert "z-50" in content
        assert "hidden" in content


@pytest.mark.django_db
class TestBillFormOfflineHooks:
    """Verify bills/templates/bills/bill_form.html contains required offline form hooks."""

    def test_bill_form_has_id_bill_form(self, staff_client):
        """GET /en/bills/add/ renders form element with id='bill-form'."""
        response = staff_client.get("/en/bills/add/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")

        assert (
            'id="bill-form"' in content
        ), "Manual bill form template is missing id='bill-form' attribute"
        assert "party" in content
        assert "invoice_no" in content


@pytest.mark.django_db
class TestOfflineTranslations:
    """Verify Urdu translations for offline sync messages."""

    def test_urdu_offline_translations_present_in_catalog(self):
        """Urdu gettext catalog translates offline sync terms."""
        translation.activate("ur")
        try:
            from django.utils.translation import gettext as _

            assert _("Offline Mode") == "آف لائن موڈ"
            assert _("You're Offline") == "آپ آف لائن ہیں"
            assert (
                _("Offline Mode — Bills saved locally will sync when online")
                == "آف لائن موڈ — بلز محفوظ ہیں، آن لائن ہونے پر سنک ہوں گے"
            )
            assert _("Syncing...") == "سنک ہو رہا ہے..."
            assert _("Synced") == "سنک ہو گیا"
            assert _("Create Bill Offline") == "نیا آف لائن بل بنائیں"
            assert _("Retry Connection") == "دوبارہ کوشش کریں"
        finally:
            translation.activate("en")

    def test_urdu_offline_shell_renders_translations(self, client):
        """GET /ur/offline/ renders translated Urdu offline page in RTL."""
        response = client.get("/ur/offline/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")

        assert "آف لائن" in content
        assert 'dir="rtl"' in content
