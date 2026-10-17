"""tests/test_landing_dynamic_settings.py
======================================
Tests for Dynamic Landing Page & Marketing Content Settings:
- LandingPageSettings singleton model creation, defaults, and video/WhatsApp helpers
- Access control: only superadmin can view and update /settings/landing/
- In-app form submission updates video URL, phone, email, headlines, pricing, and social links
- Public landing page (/en/ and /ur/) dynamically reflects backend configuration changes
- Django admin interface for LandingPageSettings
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from settings_app.models import LandingPageSettings

User = get_user_model()


@pytest.mark.django_db
class TestLandingPageSettingsModel:
    """Tests for the LandingPageSettings singleton model."""

    def test_get_solo_creates_default_instance(self):
        """get_solo() creates and returns the singleton instance with sensible defaults."""
        settings = LandingPageSettings.get_solo()
        assert settings.pk == 1
        assert settings.site_title == "ScanBooks"
        assert "Turn Paper Bills" in settings.hero_title_en
        assert "کاغذی بلوں" in settings.hero_title_ur
        assert settings.starter_scans == 10
        assert settings.pro_scans == 150
        assert settings.business_scans == 500

    def test_embed_video_url_converter(self):
        """embed_video_url converts standard YouTube and Vimeo URLs into iframe-ready embed URLs."""
        settings = LandingPageSettings.get_solo()

        # Empty URL
        settings.demo_video_url = ""
        assert settings.embed_video_url == ""

        # YouTube standard URL
        settings.demo_video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert "youtube.com/embed/dQw4w9WgXcQ?autoplay=1" in settings.embed_video_url

        # YouTube short URL
        settings.demo_video_url = "https://youtu.be/dQw4w9WgXcQ"
        assert "youtube.com/embed/dQw4w9WgXcQ?autoplay=1" in settings.embed_video_url

        # Vimeo standard URL
        settings.demo_video_url = "https://vimeo.com/123456789"
        assert "player.vimeo.com/video/123456789" in settings.embed_video_url

        # MP4 direct URL
        settings.demo_video_url = "https://example.com/demo.mp4"
        assert settings.embed_video_url == "https://example.com/demo.mp4"

    def test_clean_whatsapp_property(self):
        """clean_whatsapp extracts digits only for wa.me links."""
        settings = LandingPageSettings.get_solo()
        settings.whatsapp_number = "+92 (300) 123-4567"
        assert settings.clean_whatsapp == "923001234567"


@pytest.mark.django_db
class TestLandingPageSettingsPermissions:
    """Tests for access control on /settings/landing/."""

    def test_unauthenticated_user_redirected_to_login(self, client):
        """Unauthenticated visitor is redirected to login page."""
        url = reverse("landing_settings")
        response = client.get(url)
        assert response.status_code == 302
        assert "/login" in response.url

    def test_staff_user_forbidden(self, client, staff_user):
        """Regular staff user receives 403 Forbidden."""
        client.force_login(staff_user)
        url = reverse("landing_settings")
        response = client.get(url)
        assert response.status_code == 403

    def test_superadmin_can_access_landing_settings_page(self, client, superadmin_user):
        """Superadmin gets HTTP 200 with the settings form."""
        client.force_login(superadmin_user)
        url = reverse("landing_settings")
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Landing Page & Marketing" in content or "ہوم پیج" in content
        assert "id_demo_video_url" in content
        assert "id_support_phone" in content
        assert "id_support_email" in content


@pytest.mark.django_db
class TestLandingPageSettingsUpdateAndDisplay:
    """Tests for saving changes in backend and seeing them on the public landing page."""

    def test_update_landing_settings_via_post(self, client, superadmin_user):
        """Superadmin can update marketing settings, which updates the database."""
        client.force_login(superadmin_user)
        url = reverse("landing_settings")
        payload = {
            "site_title": "ScanBooks Pro",
            "hero_badge_en": "⚡ Next-Gen AI Scanner",
            "hero_badge_ur": "⚡ اگلی نسل کا اسکینر",
            "hero_title_en": "Transform Invoices in Seconds",
            "hero_title_ur": "چند سیکنڈوں میں انوائسز تبدیل کریں",
            "hero_subtitle_en": "Automated ledger updates without data entry.",
            "hero_subtitle_ur": "ڈیٹا انٹری کے بغیر کھاتہ خودکار بنائیں۔",
            "hero_cta_text_en": "Get 20 Free Scans Now",
            "hero_cta_text_ur": "ابھی 20 مفت اسکینز لیں",
            "free_scans_badge_count": 20,
            "demo_video_url": "https://youtu.be/dQw4w9WgXcQ",
            "video_button_text_en": "Watch 1-Minute Video",
            "video_button_text_ur": "ایک منٹ کی ویڈیو دیکھیں",
            "support_phone": "+92 311 9998877",
            "support_email": "hello@scanbooks.pk",
            "whatsapp_number": "+923119998877",
            "contact_address": "Islamabad, Pakistan",
            "contact_hours": "24/7 Priority Support",
            "starter_price_pkr": "0",
            "starter_price_usd": "0",
            "starter_scans": 20,
            "pro_price_pkr": "1,999",
            "pro_price_usd": "14.99",
            "pro_scans": 250,
            "business_price_pkr": "4,999",
            "business_price_usd": "34.99",
            "business_scans": 750,
            "facebook_url": "https://facebook.com/scanbooks",
            "twitter_url": "https://twitter.com/scanbooks",
            "linkedin_url": "https://linkedin.com/company/scanbooks",
            "instagram_url": "https://instagram.com/scanbooks",
            "youtube_url": "https://youtube.com/@scanbooks",
            "footer_text_en": "ScanBooks International Inc.",
            "footer_text_ur": "اسکین بکس انٹرنیشنل",
        }
        response = client.post(url, payload)
        assert response.status_code == 302
        assert response.url == url

        # Verify database was updated
        settings = LandingPageSettings.get_solo()
        assert settings.site_title == "ScanBooks Pro"
        assert settings.support_phone == "+92 311 9998877"
        assert settings.support_email == "hello@scanbooks.pk"
        assert settings.pro_price_pkr == "1,999"
        assert settings.pro_scans == 250

    def test_public_landing_page_displays_updated_backend_content(self, client):
        """Unauthenticated visitor sees updated dynamic content on the landing page."""
        settings = LandingPageSettings.get_solo()
        settings.support_phone = "+92 333 4445566"
        settings.support_email = "custom_contact@example.com"
        settings.demo_video_url = "https://www.youtube.com/watch?v=customvid123"
        settings.pro_price_pkr = "2,499"
        settings.hero_cta_text_en = "Start Your Exclusive 15 Scans"
        settings.save()

        # Check English page
        response_en = client.get("/en/")
        assert response_en.status_code == 200
        content_en = response_en.content.decode("utf-8")
        assert "+92 333 4445566" in content_en
        assert "custom_contact@example.com" in content_en
        assert "customvid123" in content_en
        assert "2,499" in content_en
        assert "Start Your Exclusive 15 Scans" in content_en

        # Check Urdu page
        settings.hero_cta_text_ur = "15 خاص بلز مفت اسکین کریں"
        settings.save()
        response_ur = client.get("/ur/")
        assert response_ur.status_code == 200
        content_ur = response_ur.content.decode("utf-8")
        assert "+92 333 4445566" in content_ur
        assert "custom_contact@example.com" in content_ur
        assert "15 خاص بلز مفت اسکین کریں" in content_ur
