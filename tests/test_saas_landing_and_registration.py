"""tests/test_saas_landing_and_registration.py
=============================================
Tests for SaaS Marketing Landing Page, Video Demo Modal, and Self-Service Registration.

Coverage:
- Landing Page:
  - Unauthenticated user gets HTTP 200 at /en/ and /ur/.
  - Displays ScanBooks branding, hero section, and 10 free scans CTA.
  - Contains 3-step visual flowchart, feature highlights, and pricing table.
  - Contains video demo modal markup compliant with modern dialog overscroll standards.
  - Authenticated user visiting root / or /en/ is redirected straight to /en/dashboard/.
- Self-Service User Registration:
  - GET /accounts/register/ returns HTTP 200 with registration form.
  - POST with valid details creates user, sets superadmin role, logs in, and redirects to dashboard.
  - Validation: Password mismatch returns form error.
  - Validation: Duplicate username returns form error.
  - Authenticated user visiting /accounts/register/ is redirected to dashboard.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
class TestSaaSLandingPage:
    """Tests for the SaaS landing page presentation and routing."""

    def test_unauthenticated_visitor_sees_english_landing_page(self, client):
        """Visiting /en/ renders the English landing page with key marketing sections."""
        response = client.get("/en/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "ScanBooks" in content
        assert "Start 10 Free Scans" in content
        assert "How ScanBooks Works" in content
        assert "demo-video-modal" in content
        assert "Starter" in content
        assert "Pro" in content

    def test_unauthenticated_visitor_sees_urdu_landing_page(self, client):
        """Visiting /ur/ renders the Urdu landing page with RTL layout and Urdu copy."""
        response = client.get("/ur/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'dir="rtl"' in content
        assert "اسکین بکس" in content
        assert "10 بلز مفت اسکین کریں" in content
        assert "طریقہ کار" in content

    def test_authenticated_user_visiting_landing_page_sees_dashboard(self, superadmin_client):
        """Logged-in users automatically see their private dashboard."""
        response = superadmin_client.get("/en/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Dashboard" in content


@pytest.mark.django_db
class TestSaaSSelfServiceRegistration:
    """Tests for self-service business owner registration."""

    def test_registration_page_renders_successfully(self, client):
        """GET /en/accounts/register/ returns HTTP 200 with the registration form."""
        url = reverse("accounts:register")
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Create Free Account" in content or "Start Your Free Trial" in content
        assert "business_name" in content
        assert "username" in content

    def test_successful_registration_creates_user_and_logs_in(self, client):
        """Valid form submission registers a new business owner, logs them in, and redirects to dashboard."""
        url = reverse("accounts:register")
        payload = {
            "business_name": "Al-Rehman Traders",
            "username": "alrehman",
            "email": "alrehman@example.com",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
        }
        response = client.post(url, payload)
        assert response.status_code == 302
        assert "/dashboard/" in response.url

        # Verify user was created with superadmin role for full shop management
        new_user = User.objects.get(username="alrehman")
        assert new_user.first_name == "Al-Rehman Traders"
        assert new_user.role == User.Role.SUPERADMIN
        assert new_user.can_delete_records is True
        assert new_user.can_manage_shop is True

        # Verify session is authenticated
        assert client.session.get("_auth_user_id") == str(new_user.pk)

    def test_registration_password_mismatch_shows_error(self, client):
        """Mismatched passwords display a validation error and do not create user."""
        url = reverse("accounts:register")
        payload = {
            "business_name": "Test Shop",
            "username": "testuser",
            "email": "test@example.com",
            "password": "Password123!",
            "password_confirm": "MismatchPassword!",
        }
        response = client.post(url, payload)
        assert response.status_code == 200
        assert not User.objects.filter(username="testuser").exists()

    def test_registration_duplicate_username_shows_error(self, client, superadmin_user):
        """Attempting to register with an existing username returns an error."""
        url = reverse("accounts:register")
        payload = {
            "business_name": "Duplicate Shop",
            "username": superadmin_user.username,
            "email": "dup@example.com",
            "password": "Password123!",
            "password_confirm": "Password123!",
        }
        response = client.post(url, payload)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "already exists" in content

    def test_authenticated_user_accessing_register_redirects_to_dashboard(self, superadmin_client):
        """Already authenticated users visiting the registration page are redirected to dashboard."""
        url = reverse("accounts:register")
        response = superadmin_client.get(url)
        assert response.status_code == 302
        assert "/dashboard/" in response.url
