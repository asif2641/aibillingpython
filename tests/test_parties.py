"""tests/test_parties.py
======================
Test-first test suite for Phase 3: Party Model, Fuzzy Matching, and Views.

Coverage:
- Party Model Schema & Constraints:
  - Fields: name, urdu_name, phone, email, address, tax_number, party_type, notes, is_active.
  - String representation contains name and party type.
  - Multi-language support (Urdu name and address).
  - Validation of party_type choices ('vendor', 'customer', 'both').
  - Required fields and defaults (is_active defaults to True).
- Fuzzy Matching Service (parties.services.match_or_create_party):
  - Exact match or high confidence (>= 90) returns existing party without duplicate.
  - Low similarity (< 70) creates a new party.
  - Phone number matching: matching phone returns existing party even with name variance.
  - Case-insensitivity and whitespace trimming.
  - Phone number normalization (e.g. +92 300 1234567 vs 03001234567).
  - Urdu script matching.
  - Validation: empty or None name raises error.
- Views & Access Control:
  - Unauthenticated requests redirect to login.
  - Authenticated user can view Vendors list (/en/parties/vendors/).
  - Authenticated user can view Customers list (/en/parties/customers/).
  - Authenticated user can create new party (/en/parties/add/).
  - Authenticated user can edit existing party (/en/parties/<id>/edit/).
  - Form validation failure handling on create.
  - 404 on non-existent party edit.
  - Staff user permissions check.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import NoReverseMatch, reverse

try:
    from parties.models import Party
except (ImportError, AttributeError):
    Party = None

try:
    from parties.services import match_or_create_party
except (ImportError, AttributeError):
    match_or_create_party = None

User = get_user_model()


def resolve_candidate_url(candidate_paths, reverse_names=None):
    """Resolve a URL via Django reverse if registered, or return the first candidate path."""
    if reverse_names:
        for item in reverse_names:
            if isinstance(item, tuple):
                name, args = item
            else:
                name, args = item, None
            try:
                return reverse(name, args=args)
            except (NoReverseMatch, Exception):
                pass
    return candidate_paths[0]


@pytest.fixture
def sample_vendor(db, staff_user):
    """Create a baseline vendor party."""
    assert Party is not None, "Party model is not implemented in parties.models."
    return Party.objects.create(
        user=staff_user,
        name="Al-Madina Traders",
        urdu_name="المدینہ ٹریڈرز",
        phone="03001234567",
        email="vendor@almadina.pk",
        address="Plot 12, Market Rd, Lahore",
        tax_number="1234567-8",
        party_type="vendor",
        notes="Wholesale supplier for dry goods",
        is_active=True,
    )


@pytest.fixture
def sample_customer(db, staff_user):
    """Create a baseline customer party."""
    assert Party is not None, "Party model is not implemented in parties.models."
    return Party.objects.create(
        user=staff_user,
        name="Ahmed Ali",
        urdu_name="احمد علی",
        phone="03219876543",
        email="ahmed@example.com",
        address="House 4, Street 2, Karachi",
        party_type="customer",
        notes="Regular retail customer",
        is_active=True,
    )


# ==============================================================================
# 1. Party Model Schema & Constraints Tests
# ==============================================================================


@pytest.mark.django_db
class TestPartyModelSchema:
    """Tests verifying Party model schema, fields, validation, and representations."""

    def test_party_model_exists(self):
        """Party model must be implemented and importable from parties.models."""
        assert Party is not None, "Party model is not implemented in parties.models."

    def test_party_fields_exist(self):
        """Party model must have all fields specified in the schema."""
        assert Party is not None, "Party model is missing."
        field_names = {f.name for f in Party._meta.get_fields()}
        expected_fields = {
            "name",
            "urdu_name",
            "phone",
            "email",
            "address",
            "tax_number",
            "party_type",
            "notes",
            "is_active",
        }
        missing_fields = expected_fields - field_names
        assert not missing_fields, f"Party model is missing required fields: {missing_fields}"

    def test_create_vendor_party_happy_path(self, sample_vendor):
        """Party can be created with vendor attributes and persisted correctly."""
        assert sample_vendor.pk is not None
        refreshed = Party.objects.get(pk=sample_vendor.pk)
        assert refreshed.name == "Al-Madina Traders"
        assert refreshed.urdu_name == "المدینہ ٹریڈرز"
        assert refreshed.phone == "03001234567"
        assert refreshed.email == "vendor@almadina.pk"
        assert refreshed.address == "Plot 12, Market Rd, Lahore"
        assert refreshed.tax_number == "1234567-8"
        assert refreshed.party_type == "vendor"
        assert refreshed.is_active is True

    def test_create_customer_party_happy_path(self, sample_customer):
        """Party can be created with customer attributes and persisted correctly."""
        assert sample_customer.pk is not None
        refreshed = Party.objects.get(pk=sample_customer.pk)
        assert refreshed.name == "Ahmed Ali"
        assert refreshed.party_type == "customer"
        assert refreshed.phone == "03219876543"

    def test_party_str_representation_contains_name_and_party_type(self, sample_vendor):
        """Party string representation must contain party name and party type."""
        str_repr = str(sample_vendor)
        assert "Al-Madina Traders" in str_repr
        assert "vendor" in str_repr.lower()

    def test_party_type_choices(self):
        """party_type field must support 'vendor', 'customer', and 'both'."""
        assert Party is not None, "Party model is missing."
        for p_type in ["vendor", "customer", "both"]:
            party = Party.objects.create(name=f"Party {p_type}", party_type=p_type)
            assert party.party_type == p_type
            party.full_clean()  # Should not raise ValidationError

    def test_party_invalid_party_type_raises_error(self):
        """Invalid party_type choice raises ValidationError on full_clean()."""
        assert Party is not None, "Party model is missing."
        party = Party(name="Invalid Type Store", party_type="distributor")
        with pytest.raises(ValidationError):
            party.full_clean()

    def test_party_urdu_multilingual_support(self):
        """Party supports full Urdu Unicode text in name, urdu_name, and address."""
        assert Party is not None, "Party model is missing."
        urdu_party = Party.objects.create(
            name="Al-Haramain General Store",
            urdu_name="الحرمین جنرل اسٹور",
            address="دکان نمبر ۵، غلہ منڈی، ملتان",
            party_type="vendor",
        )
        refreshed = Party.objects.get(pk=urdu_party.pk)
        assert refreshed.urdu_name == "الحرمین جنرل اسٹور"
        assert "غلہ منڈی" in refreshed.address

    def test_party_blank_optional_fields_defaults(self):
        """Party can be created with only the name field, other optional fields blank."""
        assert Party is not None, "Party model is missing."
        party = Party.objects.create(name="Minimalist Trading")
        assert party.pk is not None
        assert party.is_active is True
        assert party.phone == "" or party.phone is None
        assert party.email == "" or party.email is None

    def test_party_empty_name_raises_validation_error(self):
        """Empty party name raises ValidationError."""
        assert Party is not None, "Party model is missing."
        party = Party(name="")
        with pytest.raises(ValidationError):
            party.full_clean()

    def test_party_active_filtering(self, sample_vendor):
        """Inactive parties can be filtered out from active querysets."""
        inactive_party = Party.objects.create(
            name="Closed Business", party_type="vendor", is_active=False
        )
        active_parties = Party.objects.filter(is_active=True)
        assert sample_vendor in active_parties
        assert inactive_party not in active_parties


# ==============================================================================
# 2. Fuzzy Matching Service Tests
# ==============================================================================


@pytest.mark.django_db
class TestPartyFuzzyMatchingService:
    """Tests for parties.services.match_or_create_party fuzzy matching."""

    def test_fuzzy_matching_service_exists(self):
        """match_or_create_party function must be implemented in parties.services."""
        assert (
            match_or_create_party is not None
        ), "match_or_create_party function is not implemented in parties.services."

    def test_exact_name_match_returns_existing_party(self, sample_vendor):
        """Exact name match returns the existing party without creating a duplicate."""
        assert match_or_create_party is not None, "match_or_create_party is missing."
        initial_count = Party.objects.count()
        result = match_or_create_party(name="Al-Madina Traders", party_type="vendor")
        matched_party = result[0] if isinstance(result, tuple) else result

        assert matched_party.pk == sample_vendor.pk
        assert Party.objects.count() == initial_count

    def test_case_insensitive_and_whitespace_variance_match(self, sample_vendor):
        """Name match succeeds despite case differences and surrounding whitespace."""
        assert match_or_create_party is not None, "match_or_create_party is missing."
        initial_count = Party.objects.count()
        result = match_or_create_party(name="   al-madina traders   ", party_type="vendor")
        matched_party = result[0] if isinstance(result, tuple) else result

        assert matched_party.pk == sample_vendor.pk
        assert Party.objects.count() == initial_count

    def test_high_confidence_fuzzy_name_match(self, sample_vendor):
        """Minor spelling variance (similarity >= 90) returns existing party."""
        assert match_or_create_party is not None, "match_or_create_party is missing."
        initial_count = Party.objects.count()
        # "Al Madina Traders" vs "Al-Madina Traders" (hyphen missing)
        result = match_or_create_party(name="Al Madina Traders", party_type="vendor")
        matched_party = result[0] if isinstance(result, tuple) else result

        assert matched_party.pk == sample_vendor.pk
        assert Party.objects.count() == initial_count

    def test_phone_number_matching_with_name_variance(self, sample_vendor):
        """Matching phone number returns existing party even if name has variation."""
        assert match_or_create_party is not None, "match_or_create_party is missing."
        initial_count = Party.objects.count()
        result = match_or_create_party(
            name="Madinah General Store",
            phone="03001234567",
            party_type="vendor",
        )
        matched_party = result[0] if isinstance(result, tuple) else result

        assert matched_party.pk == sample_vendor.pk
        assert Party.objects.count() == initial_count

    def test_phone_number_formatting_normalization(self, sample_vendor):
        """Phone matching normalizes formatting differences (spaces, dashes, country code)."""
        assert match_or_create_party is not None, "match_or_create_party is missing."
        initial_count = Party.objects.count()
        # "+92 300 1234567" vs "03001234567"
        result = match_or_create_party(
            name="Al-Madina Traders",
            phone="+92 300 1234567",
            party_type="vendor",
        )
        matched_party = result[0] if isinstance(result, tuple) else result

        assert matched_party.pk == sample_vendor.pk
        assert Party.objects.count() == initial_count

    def test_low_similarity_creates_new_party(self, sample_vendor):
        """Low similarity (< 70) creates a new party record instead of matching."""
        assert match_or_create_party is not None, "match_or_create_party is missing."
        initial_count = Party.objects.count()
        result = match_or_create_party(
            name="National Electric Supply",
            phone="03339999999",
            party_type="vendor",
        )
        new_party = result[0] if isinstance(result, tuple) else result

        assert new_party.pk != sample_vendor.pk
        assert new_party.name == "National Electric Supply"
        assert Party.objects.count() == initial_count + 1

    def test_urdu_name_matching(self, sample_vendor):
        """Urdu name match returns existing party."""
        assert match_or_create_party is not None, "match_or_create_party is missing."
        initial_count = Party.objects.count()
        result = match_or_create_party(name="المدینہ ٹریڈرز", party_type="vendor")
        matched_party = result[0] if isinstance(result, tuple) else result

        assert matched_party.pk == sample_vendor.pk
        assert Party.objects.count() == initial_count

    def test_matching_preserves_or_sets_requested_party_type(self):
        """When creating a new party, requested party_type is preserved."""
        assert match_or_create_party is not None, "match_or_create_party is missing."
        result = match_or_create_party(name="New Customer Person", party_type="customer")
        party = result[0] if isinstance(result, tuple) else result

        assert party.party_type == "customer"

    def test_empty_or_none_name_raises_error(self):
        """Empty string or None as name raises ValueError or ValidationError."""
        assert match_or_create_party is not None, "match_or_create_party is missing."
        with pytest.raises((ValueError, ValidationError)):
            match_or_create_party(name="")
        with pytest.raises((ValueError, ValidationError)):
            match_or_create_party(name=None)


# ==============================================================================
# 3. Party Views & Access Control Tests
# ==============================================================================


@pytest.mark.django_db
class TestPartyViewsAndAccessControl:
    """Tests for Party views, URLs, permissions, and forms."""

    VENDORS_URL_CANDIDATES = ["/en/parties/vendors/"]
    VENDORS_REVERSE_NAMES = ["parties:vendor_list", "parties:vendors", "parties:vendor-list"]

    CUSTOMERS_URL_CANDIDATES = ["/en/parties/customers/"]
    CUSTOMERS_REVERSE_NAMES = [
        "parties:customer_list",
        "parties:customers",
        "parties:customer-list",
    ]

    ADD_URL_CANDIDATES = ["/en/parties/add/"]
    ADD_REVERSE_NAMES = ["parties:party_create", "parties:party_add", "parties:add"]

    def _vendors_url(self):
        return resolve_candidate_url(self.VENDORS_URL_CANDIDATES, self.VENDORS_REVERSE_NAMES)

    def _customers_url(self):
        return resolve_candidate_url(self.CUSTOMERS_URL_CANDIDATES, self.CUSTOMERS_REVERSE_NAMES)

    def _add_url(self):
        return resolve_candidate_url(self.ADD_URL_CANDIDATES, self.ADD_REVERSE_NAMES)

    def _edit_url(self, party_id):
        return resolve_candidate_url(
            [f"/en/parties/{party_id}/edit/"],
            [("parties:party_edit", [party_id]), ("parties:edit", [party_id])],
        )

    def test_unauthenticated_requests_redirect_to_login(self, client, sample_vendor):
        """Unauthenticated requests to party views redirect to the login page."""
        for url in [
            self._vendors_url(),
            self._customers_url(),
            self._add_url(),
            self._edit_url(sample_vendor.pk),
        ]:
            response = client.get(url)
            assert response.status_code == 302, f"Expected 302 redirect for unauth {url}"
            assert "/accounts/login/" in response.url

    def test_authenticated_user_can_view_vendors_list(
        self, staff_client, sample_vendor, sample_customer
    ):
        """Authenticated user can view Vendors list, which shows vendors and excludes customer-only."""
        response = staff_client.get(self._vendors_url())
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert sample_vendor.name in content
        # Pure customer should not appear in vendors list
        assert sample_customer.name not in content

    def test_authenticated_user_can_view_customers_list(
        self, staff_client, sample_vendor, sample_customer
    ):
        """Authenticated user can view Customers list, which shows customers and excludes vendor-only."""
        response = staff_client.get(self._customers_url())
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert sample_customer.name in content
        # Pure vendor should not appear in customers list
        assert sample_vendor.name not in content

    def test_party_with_both_type_appears_in_both_lists(self, staff_client, staff_user):
        """Party marked with party_type='both' appears in both vendors and customers lists."""
        assert Party is not None, "Party model is missing."
        both_party = Party.objects.create(
            name="Dual Purpose Merchant", party_type="both", user=staff_user
        )

        resp_vendors = staff_client.get(self._vendors_url())
        assert resp_vendors.status_code == 200
        assert both_party.name in resp_vendors.content.decode("utf-8")

        resp_customers = staff_client.get(self._customers_url())
        assert resp_customers.status_code == 200
        assert both_party.name in resp_customers.content.decode("utf-8")

    def test_authenticated_user_can_create_new_vendor(self, staff_client):
        """Authenticated user can GET party add form and POST to create a new vendor."""
        # GET form
        response = staff_client.get(self._add_url())
        assert response.status_code == 200

        # POST valid vendor
        payload = {
            "name": "Khyber Cement Wholesalers",
            "urdu_name": "خیبر سیمنٹ ہول سیلر",
            "phone": "03331122334",
            "email": "khyber@example.com",
            "address": "Ring Road, Peshawar",
            "tax_number": "NTN-987654",
            "party_type": "vendor",
            "notes": "Payment terms: net 30",
        }
        post_resp = staff_client.post(self._add_url(), payload)
        assert post_resp.status_code in (302, 201)

        assert Party.objects.filter(name="Khyber Cement Wholesalers").exists()
        created = Party.objects.get(name="Khyber Cement Wholesalers")
        assert created.party_type == "vendor"
        assert created.phone == "03331122334"

    def test_authenticated_user_can_create_new_customer(self, staff_client):
        """Authenticated user can POST to create a customer party."""
        payload = {
            "name": "Fatima Noor",
            "urdu_name": "فاطمہ نور",
            "phone": "03456789012",
            "email": "fatima@example.com",
            "address": "Sector F-7, Islamabad",
            "party_type": "customer",
        }
        post_resp = staff_client.post(self._add_url(), payload)
        assert post_resp.status_code in (302, 201)

        assert Party.objects.filter(name="Fatima Noor", party_type="customer").exists()

    def test_create_party_form_validation_error(self, staff_client):
        """Posting invalid data (e.g. empty name) returns form errors and does not create party."""
        initial_count = Party.objects.count() if Party else 0
        payload = {
            "name": "",  # Name is required
            "party_type": "vendor",
        }
        response = staff_client.post(self._add_url(), payload)
        # Form error usually renders 200 (re-rendering form with errors) or 400
        assert response.status_code in (200, 400)
        if Party is not None:
            assert Party.objects.count() == initial_count

    def test_authenticated_user_can_edit_existing_party(self, staff_client, sample_vendor):
        """Authenticated user can GET edit form and POST updates to an existing party."""
        edit_url = self._edit_url(sample_vendor.pk)
        get_resp = staff_client.get(edit_url)
        assert get_resp.status_code == 200

        update_payload = {
            "name": "Al-Madina Traders Updated",
            "urdu_name": "المدینہ ٹریڈرز",
            "phone": "03009998877",
            "email": "updated@almadina.pk",
            "address": "New Shop 5, Market Rd, Lahore",
            "tax_number": "1234567-8",
            "party_type": "vendor",
            "notes": "Updated contact info",
            "is_active": True,
        }
        post_resp = staff_client.post(edit_url, update_payload)
        assert post_resp.status_code in (302, 200)

        sample_vendor.refresh_from_db()
        assert sample_vendor.name == "Al-Madina Traders Updated"
        assert sample_vendor.phone == "03009998877"

    def test_edit_nonexistent_party_returns_404(self, staff_client):
        """Attempting to edit a non-existent party ID returns HTTP 404."""
        assert Party is not None, "Party model is missing."
        edit_url = self._edit_url(999999)
        response = staff_client.get(edit_url)
        assert response.status_code == 404

    def test_superadmin_has_full_party_management_access(self, superadmin_client, sample_vendor):
        """Superadmin can view and edit parties."""
        response = superadmin_client.get(self._vendors_url())
        assert response.status_code == 200
        edit_resp = superadmin_client.get(self._edit_url(sample_vendor.pk))
        assert edit_resp.status_code == 200

    def test_delete_party_deactivates_and_redirects(self, staff_client, sample_vendor):
        """POSTing to party delete route deactivates the party and removes from active vendor list."""
        delete_url = reverse("parties:party_delete", kwargs={"pk": sample_vendor.pk})
        resp = staff_client.post(delete_url)
        assert resp.status_code == 302
        sample_vendor.refresh_from_db()
        assert sample_vendor.is_active is False

        # Inactive party should not appear in active vendor list
        list_resp = staff_client.get(self._vendors_url())
        assert sample_vendor not in list_resp.context["parties"].object_list

    def test_multi_tenant_party_isolation(self, client, db):
        """Tenants must only see, edit, and match their own parties."""
        user_a = User.objects.create_user(
            username="tenant_a",
            email="tenant_a@example.com",
            password="TestPassword123!",
            role=User.Role.STAFF,
        )
        user_b = User.objects.create_user(
            username="tenant_b",
            email="tenant_b@example.com",
            password="TestPassword123!",
            role=User.Role.STAFF,
        )

        vendor_a = Party.objects.create(
            name="Vendor Of User A",
            party_type=Party.PartyType.VENDOR,
            user=user_a,
        )
        customer_a = Party.objects.create(
            name="Customer Of User A",
            party_type=Party.PartyType.CUSTOMER,
            user=user_a,
        )

        vendor_b = Party.objects.create(
            name="Vendor Of User B",
            party_type=Party.PartyType.VENDOR,
            user=user_b,
        )
        customer_b = Party.objects.create(
            name="Customer Of User B",
            party_type=Party.PartyType.CUSTOMER,
            user=user_b,
        )

        # 1. User A sees only User A's parties
        client.force_login(user_a)
        resp_v_a = client.get(self._vendors_url())
        assert resp_v_a.status_code == 200
        vendor_list_a = resp_v_a.context["parties"].object_list
        assert vendor_a in vendor_list_a
        assert vendor_b not in vendor_list_a

        resp_c_a = client.get(self._customers_url())
        assert resp_c_a.status_code == 200
        customer_list_a = resp_c_a.context["parties"].object_list
        assert customer_a in customer_list_a
        assert customer_b not in customer_list_a

        # 2. User B sees only User B's parties
        client.force_login(user_b)
        resp_v_b = client.get(self._vendors_url())
        assert resp_v_b.status_code == 200
        vendor_list_b = resp_v_b.context["parties"].object_list
        assert vendor_b in vendor_list_b
        assert vendor_a not in vendor_list_b

        # 3. User B cannot edit or delete User A's party
        edit_resp = client.get(self._edit_url(vendor_a.pk))
        assert edit_resp.status_code == 404

        del_url = reverse("parties:party_delete", kwargs={"pk": vendor_a.pk})
        del_resp = client.post(del_url)
        assert del_resp.status_code == 404
        vendor_a.refresh_from_db()
        assert vendor_a.is_active is True

        # 4. Fuzzy match for User B does NOT return User A's party
        matched = match_or_create_party("Vendor Of User A", user=user_b)
        assert matched.pk != vendor_a.pk
        assert matched.user == user_b
