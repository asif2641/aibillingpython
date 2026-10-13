"""tests/test_shop_profile.py
===========================
Tests for Phase 2: Shop Profile Model, Singleton Pattern, and Settings Views.

Coverage:
- ShopProfile Model:
  - Singleton behavior: ShopProfile.get_solo() creates instance if none exists,
    or retrieves the existing single instance.
  - Calling get_solo() multiple times returns the identical record.
  - Singleton enforcement on save/create prevents multiple records.
  - Fields present and verified:
    name, address, phone, email, tax_number, currency, timezone,
    date_format, default_language, invoice_footer_text,
    daily_scan_limit, monthly_scan_limit.
  - Urdu and multi-lingual text support (RTL shop name, address, footer).
  - Boundary scan limits: zero limits (0), large limits, negative validation.
- Access Control & Views:
  - Unauthenticated access to /en/settings/shop/ is redirected to login.
  - Superadmin can GET /en/settings/shop/ (HTTP 200) and view shop profile form.
  - Superadmin can POST updates to /en/settings/shop/ to update shop name,
    currency, tax number, scan limits, etc.
  - Staff user WITHOUT can_manage_shop permission is denied access (HTTP 403 or redirect).
  - Staff user WITH can_manage_shop=True can successfully view and update shop profile.
- Edge Cases & Validation:
  - Invalid email format fails validation.
  - Negative daily/monthly scan limit fails validation.
  - Empty required fields fail validation.
  - Urdu/Unicode content submitted via form is preserved without corruption.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

# Attempt to import ShopProfile from settings_app.models.
# In test-first development, this may be None until implemented by backend.
try:
    from settings_app.models import ShopProfile
except (ImportError, AttributeError):
    ShopProfile = None

User = get_user_model()


@pytest.fixture
def sample_shop_data():
    """Valid baseline dictionary for shop profile fields."""
    return {
        "name": "Al-Madina Super Store",
        "address": "Shop 4, Commercial Market, Lahore",
        "phone": "+92 300 1234567",
        "email": "shop@almadina.example.com",
        "tax_number": "NTN-1234567-8",
        "currency": "PKR",
        "timezone": "Asia/Karachi",
        "date_format": "YYYY-MM-DD",
        "default_language": "en",
        "invoice_footer_text": "Thank you for shopping with us! No return without receipt.",
        "daily_scan_limit": 50,
        "monthly_scan_limit": 1000,
    }


def create_staff_with_shop_permission():
    """Create a staff user explicitly granted can_manage_shop permission."""
    assert hasattr(
        User, "can_manage_shop"
    ), "User model must define 'can_manage_shop' boolean permission field."
    return User.objects.create_user(
        username="shop_manager_staff",
        email="shopmgr@example.com",
        password="TestPass123!",
        role=User.Role.STAFF,
        can_manage_shop=True,
    )


@pytest.mark.django_db
class TestShopProfileModel:
    """Unit tests for the ShopProfile singleton model and its fields."""

    def test_shop_profile_model_exists(self):
        """ShopProfile model must be implemented in settings_app.models."""
        assert (
            ShopProfile is not None
        ), "ShopProfile model is not implemented in settings_app.models."

    def test_shop_profile_singleton_get_solo_creates_if_empty(self):
        """ShopProfile.get_solo() creates the single instance when DB is empty."""
        assert ShopProfile is not None, "ShopProfile model is missing."
        assert hasattr(
            ShopProfile, "get_solo"
        ), "ShopProfile must provide a 'get_solo()' classmethod for singleton access."

        assert ShopProfile.objects.count() == 0
        profile = ShopProfile.get_solo()
        assert profile is not None
        assert profile.pk is not None
        assert ShopProfile.objects.count() == 1

    def test_shop_profile_singleton_get_solo_returns_same_instance(self):
        """Subsequent calls to get_solo() return the exact same instance."""
        assert ShopProfile is not None, "ShopProfile model is missing."
        profile1 = ShopProfile.get_solo()
        profile2 = ShopProfile.get_solo()

        assert profile1.pk == profile2.pk
        assert ShopProfile.objects.count() == 1

    def test_shop_profile_singleton_enforces_single_row(self, sample_shop_data):
        """Singleton pattern ensures multiple instances cannot coexist in the database."""
        assert ShopProfile is not None, "ShopProfile model is missing."
        profile = ShopProfile.get_solo()
        for key, val in sample_shop_data.items():
            setattr(profile, key, val)
        profile.save()

        # Attempting to create a second instance should either update the singleton
        # or raise an exception rather than creating row 2.
        try:
            second_instance = ShopProfile(name="Duplicate Shop")
            second_instance.save()
            assert (
                ShopProfile.objects.count() == 1
            ), "ShopProfile should enforce singleton: count must remain 1."
            assert ShopProfile.get_solo().pk == profile.pk
        except (ValidationError, Exception):
            # Raising an error on duplicate creation is also an acceptable singleton pattern
            assert ShopProfile.objects.count() == 1

    def test_shop_profile_all_expected_fields_exist(self, sample_shop_data):
        """ShopProfile must contain all fields specified in the master prompt."""
        assert ShopProfile is not None, "ShopProfile model is missing."
        profile = ShopProfile.get_solo()

        expected_fields = [
            "name",
            "address",
            "phone",
            "email",
            "tax_number",
            "currency",
            "timezone",
            "date_format",
            "default_language",
            "invoice_footer_text",
            "daily_scan_limit",
            "monthly_scan_limit",
        ]
        for field_name in expected_fields:
            assert hasattr(
                profile, field_name
            ), f"ShopProfile model is missing required field: '{field_name}'"

        # Set all values, save, and verify persistence
        for field_name, value in sample_shop_data.items():
            setattr(profile, field_name, value)
        profile.save()

        refreshed = ShopProfile.objects.get(pk=profile.pk)
        for field_name, expected_value in sample_shop_data.items():
            assert (
                getattr(refreshed, field_name) == expected_value
            ), f"Field '{field_name}' did not persist expected value."

    def test_shop_profile_urdu_text_support(self):
        """ShopProfile must properly store and return Urdu Unicode text."""
        assert ShopProfile is not None, "ShopProfile model is missing."
        profile = ShopProfile.get_solo()
        urdu_name = "المدینہ سپر سٹور"
        urdu_address = "دکان نمبر ۴، مین کمرشل مارکیٹ، لاہور"
        urdu_footer = "خریداری کا شکریہ! بل کے بغیر کوئی واپسی نہیں۔"

        profile.name = urdu_name
        profile.address = urdu_address
        profile.invoice_footer_text = urdu_footer
        profile.default_language = "ur"
        profile.save()

        refreshed = ShopProfile.objects.get(pk=profile.pk)
        assert refreshed.name == urdu_name
        assert refreshed.address == urdu_address
        assert refreshed.invoice_footer_text == urdu_footer
        assert refreshed.default_language == "ur"

    def test_shop_profile_scan_limits_boundaries(self):
        """Scan limit edge cases: zero limit, large limit, and negative limit validation."""
        assert ShopProfile is not None, "ShopProfile model is missing."
        profile = ShopProfile.get_solo()

        # Boundary: zero limits (disabled or quota exhausted)
        profile.daily_scan_limit = 0
        profile.monthly_scan_limit = 0
        profile.save()
        refreshed = ShopProfile.objects.get(pk=profile.pk)
        assert refreshed.daily_scan_limit == 0
        assert refreshed.monthly_scan_limit == 0

        # Boundary: high limits
        profile.daily_scan_limit = 50000
        profile.monthly_scan_limit = 1000000
        profile.save()
        refreshed = ShopProfile.objects.get(pk=profile.pk)
        assert refreshed.daily_scan_limit == 50000
        assert refreshed.monthly_scan_limit == 1000000

        # Boundary: negative scan limits should fail validation
        profile.daily_scan_limit = -5
        with pytest.raises(ValidationError):
            profile.full_clean()

    def test_shop_profile_str_representation(self):
        """str(ShopProfile) should return a readable string containing the shop name."""
        assert ShopProfile is not None, "ShopProfile model is missing."
        profile = ShopProfile.get_solo()
        profile.name = "Madina Cash & Carry"
        profile.save()
        assert "Madina Cash & Carry" in str(profile)


@pytest.mark.django_db
class TestShopProfileAccessControl:
    """Integration tests for /en/settings/shop/ view and access permissions."""

    SHOP_URL = "/en/settings/shop/"

    def test_unauthenticated_user_redirected_to_login(self, client):
        """Unauthenticated user accessing /en/settings/shop/ is redirected to login."""
        response = client.get(self.SHOP_URL)
        assert response.status_code == 302
        assert "/login" in response.url or reverse("accounts:login") in response.url

        # POST attempt is also redirected
        post_response = client.post(self.SHOP_URL, {"name": "Hacked Shop"})
        assert post_response.status_code == 302

    def test_superadmin_can_view_shop_profile_page(self, superadmin_client):
        """Superadmin can GET /en/settings/shop/ and see the configuration form."""
        response = superadmin_client.get(self.SHOP_URL)
        assert response.status_code == 200
        # Page should render form inputs for shop profile
        content = response.content.decode("utf-8")
        assert "name" in content.lower()
        assert "currency" in content.lower()

    def test_superadmin_can_update_shop_profile(self, superadmin_client, sample_shop_data):
        """Superadmin can POST updates to /en/settings/shop/ and update the database."""
        assert ShopProfile is not None, "ShopProfile model is missing."
        response = superadmin_client.post(self.SHOP_URL, sample_shop_data)
        # Should redirect after POST or return 200
        assert response.status_code in [200, 302]

        profile = ShopProfile.get_solo()
        assert profile.name == sample_shop_data["name"]
        assert profile.currency == sample_shop_data["currency"]
        assert profile.tax_number == sample_shop_data["tax_number"]
        assert profile.daily_scan_limit == sample_shop_data["daily_scan_limit"]

    def test_staff_without_can_manage_shop_is_denied(self, staff_client, sample_shop_data):
        """Staff user without can_manage_shop permission receives 403 or redirect."""
        # GET should be forbidden or redirected
        response = staff_client.get(self.SHOP_URL)
        assert response.status_code in [403, 302]

        # POST should be rejected and changes must NOT be saved
        original_name = "Original Shop Name"
        if ShopProfile is not None:
            profile = ShopProfile.get_solo()
            profile.name = original_name
            profile.save()

        malicious_data = sample_shop_data.copy()
        malicious_data["name"] = "Unauthorized Staff Edit"
        post_response = staff_client.post(self.SHOP_URL, malicious_data)
        assert post_response.status_code in [403, 302]

        if ShopProfile is not None:
            profile.refresh_from_db()
            assert profile.name == original_name

    def test_staff_with_can_manage_shop_can_view_and_update(self, client, sample_shop_data):
        """Staff user with can_manage_shop=True can successfully view and update."""
        assert ShopProfile is not None, "ShopProfile model is missing."
        staff_user = create_staff_with_shop_permission()
        client.force_login(staff_user)

        # GET request succeeds
        get_response = client.get(self.SHOP_URL)
        assert get_response.status_code == 200

        # POST request succeeds and updates settings
        post_response = client.post(self.SHOP_URL, sample_shop_data)
        assert post_response.status_code in [200, 302]

        profile = ShopProfile.get_solo()
        assert profile.name == sample_shop_data["name"]
        assert profile.email == sample_shop_data["email"]


@pytest.mark.django_db
class TestShopProfileValidationAndEdgeCases:
    """Edge cases, form validation, and boundary conditions for shop settings."""

    SHOP_URL = "/en/settings/shop/"

    def test_post_invalid_email_format_fails_validation(self, superadmin_client, sample_shop_data):
        """Submitting an invalid email address triggers validation error."""
        assert ShopProfile is not None, "ShopProfile model is missing."
        profile = ShopProfile.get_solo()
        profile.email = "valid@example.com"
        profile.save()

        invalid_data = sample_shop_data.copy()
        invalid_data["email"] = "not-an-email"

        response = superadmin_client.post(self.SHOP_URL, invalid_data)
        # Should not crash (no 500) and email in DB should not be updated to invalid string
        assert response.status_code in [200, 400]
        profile.refresh_from_db()
        assert profile.email != "not-an-email"

    def test_post_negative_scan_limit_fails_validation(self, superadmin_client, sample_shop_data):
        """Submitting negative scan limits is rejected with validation error."""
        assert ShopProfile is not None, "ShopProfile model is missing."
        profile = ShopProfile.get_solo()
        profile.daily_scan_limit = 50
        profile.save()

        invalid_data = sample_shop_data.copy()
        invalid_data["daily_scan_limit"] = -10

        response = superadmin_client.post(self.SHOP_URL, invalid_data)
        assert response.status_code in [200, 400]
        profile.refresh_from_db()
        assert profile.daily_scan_limit >= 0

    def test_post_urdu_text_via_form_persists_correctly(self, superadmin_client, sample_shop_data):
        """Urdu characters submitted via POST form are stored cleanly in database."""
        assert ShopProfile is not None, "ShopProfile model is missing."
        urdu_data = sample_shop_data.copy()
        urdu_data["name"] = "بسم اللہ جنرل سٹور"
        urdu_data["address"] = "بازار نمبر ۲، راولپنڈی"
        urdu_data["invoice_footer_text"] = "دوبارہ تشریف لائیں۔ شکریہ!"
        urdu_data["default_language"] = "ur"

        response = superadmin_client.post(self.SHOP_URL, urdu_data)
        assert response.status_code in [200, 302]

        profile = ShopProfile.get_solo()
        assert profile.name == "بسم اللہ جنرل سٹور"
        assert profile.invoice_footer_text == "دوبارہ تشریف لائیں۔ شکریہ!"
        assert profile.default_language == "ur"

    def test_post_empty_required_shop_name_fails_validation(
        self, superadmin_client, sample_shop_data
    ):
        """Submitting an empty shop name is rejected when name is required."""
        assert ShopProfile is not None, "ShopProfile model is missing."
        profile = ShopProfile.get_solo()
        profile.name = "Non-empty Shop"
        profile.save()

        empty_name_data = sample_shop_data.copy()
        empty_name_data["name"] = ""

        response = superadmin_client.post(self.SHOP_URL, empty_name_data)
        assert response.status_code in [200, 400]
        profile.refresh_from_db()
        assert profile.name == "Non-empty Shop"
