"""tests/test_categories_units.py
================================
Tests for Phase 2: Category and Unit Models, Seeding, and Views.

Coverage:
- Category Model:
  - Fields: name, urdu_name, color (hex code), is_archived.
  - Name uniqueness and str representation.
  - Hex color formatting (e.g. #3B82F6).
  - Urdu and Unicode text support.
  - Soft archiving: toggling is_archived filters from active querysets.
- Category Seeding:
  - Default categories seeded: Grocery, Medical, Utilities, Fuel,
    Electronics, Clothing, Restaurant, Construction, Stationery, Other.
  - Each seeded category has both English and Urdu names.
  - Seeding idempotency (running twice does not create duplicate records).
- Category Views & Access Control:
  - Superadmin can view category list.
  - Superadmin can create a new category (name, urdu_name, color).
  - Superadmin can edit an existing category.
  - Superadmin can toggle is_archived on a category.
  - Staff user WITH can_manage_categories=True can manage categories.
  - Staff user WITHOUT can_manage_categories is denied access (HTTP 403 or redirect).
  - Unauthenticated access redirects to login.
- Unit Model & Seeding:
  - Standard units seeded: pcs, ltr, ml, g, kg, ton, dozen, box, meter.
  - Seeding idempotency.
  - Custom unit creation (name, code, urdu_name).
  - Code uniqueness constraint.
  - Staff without can_manage_categories denied adding units.
  - Staff with can_manage_categories can add custom units.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import NoReverseMatch, reverse

# Attempt to import Category and Unit from categories.models
try:
    from categories.models import Category
except (ImportError, AttributeError):
    Category = None

try:
    from categories.models import Unit
except (ImportError, AttributeError):
    Unit = None

User = get_user_model()

DEFAULT_CATEGORY_NAMES = [
    "Grocery",
    "Medical",
    "Utilities",
    "Fuel",
    "Electronics",
    "Clothing",
    "Restaurant",
    "Construction",
    "Stationery",
    "Other",
]

STANDARD_UNIT_CODES = [
    "pcs",
    "ltr",
    "ml",
    "g",
    "kg",
    "ton",
    "dozen",
    "box",
    "meter",
]


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


def run_category_seeding():
    """Execute category seeding via service function, model classmethod, or command."""
    # Option 1: categories.services.seed_default_categories
    try:
        from categories import services

        if hasattr(services, "seed_default_categories"):
            return services.seed_default_categories()
    except (ImportError, AttributeError):
        pass

    # Option 2: Category.seed_defaults()
    if Category is not None and hasattr(Category, "seed_defaults"):
        return Category.seed_defaults()

    # Option 3: Management command 'seed_categories' or 'seed_defaults'
    from django.core.management import call_command

    for cmd in ["seed_categories", "seed_defaults"]:
        try:
            return call_command(cmd)
        except Exception:
            pass

    pytest.fail(
        "No category seeding mechanism found. Implement seed_default_categories() in "
        "categories.services or Category.seed_defaults() or a management command."
    )


def run_unit_seeding():
    """Execute unit seeding via service function, model classmethod, or command."""
    try:
        from categories import services

        if hasattr(services, "seed_default_units"):
            return services.seed_default_units()
    except (ImportError, AttributeError):
        pass

    if Unit is not None and hasattr(Unit, "seed_defaults"):
        return Unit.seed_defaults()

    from django.core.management import call_command

    for cmd in ["seed_units", "seed_defaults"]:
        try:
            return call_command(cmd)
        except Exception:
            pass

    pytest.fail(
        "No unit seeding mechanism found. Implement seed_default_units() in "
        "categories.services or Unit.seed_defaults() or a management command."
    )


def create_staff_with_category_permission():
    """Create a staff user granted can_manage_categories permission."""
    assert hasattr(
        User, "can_manage_categories"
    ), "User model must define 'can_manage_categories' boolean permission field."
    return User.objects.create_user(
        username="category_manager",
        email="catmgr@example.com",
        password="TestPass123!",
        role=User.Role.STAFF,
        can_manage_categories=True,
    )


def create_sample_category():
    """Create a baseline Category instance."""
    assert Category is not None, "Category model is missing in categories.models."
    return Category.objects.create(
        name="Groceries",
        urdu_name="کریانہ",
        color="#3B82F6",
        is_archived=False,
    )


@pytest.mark.django_db
class TestCategoryModel:
    """Unit tests for the Category model schema, validation, and methods."""

    def test_category_model_exists(self):
        """Category model must be implemented in categories.models."""
        assert Category is not None, "Category model is not implemented in categories.models."

    def test_create_category_with_urdu_and_hex_color(self):
        """Category successfully persists name, urdu_name, hex color, and archive status."""
        assert Category is not None, "Category model is missing."
        cat = Category.objects.create(
            name="Medical",
            urdu_name="ادویات",
            color="#EF4444",
            is_archived=False,
        )
        assert cat.pk is not None
        refreshed = Category.objects.get(pk=cat.pk)
        assert refreshed.name == "Medical"
        assert refreshed.urdu_name == "ادویات"
        assert refreshed.color.upper() == "#EF4444"
        assert refreshed.is_archived is False

    def test_category_str_representation(self):
        """str(Category) contains the category name."""
        category = create_sample_category()
        assert category.name in str(category)

    def test_category_unique_name_constraint(self):
        """Duplicate category names must be rejected."""
        category = create_sample_category()
        with pytest.raises((IntegrityError, ValidationError)):
            duplicate = Category(name=category.name, color="#10B981")
            duplicate.full_clean()
            duplicate.save()

    def test_category_hex_color_validation(self):
        """Category color should validate hex color format (e.g. #3B82F6)."""
        assert Category is not None, "Category model is missing."
        cat = Category(name="Electronics", color="invalid-hex")
        if hasattr(cat, "clean"):
            with pytest.raises(ValidationError):
                cat.full_clean()

    def test_category_is_archived_filtering(self):
        """Archived categories can be filtered out from active category queries."""
        assert Category is not None, "Category model is missing."
        active = Category.objects.create(name="Active Cat", color="#3B82F6", is_archived=False)
        archived = Category.objects.create(name="Archived Cat", color="#64748B", is_archived=True)

        active_queryset = Category.objects.filter(is_archived=False)
        assert active in active_queryset
        assert archived not in active_queryset


@pytest.mark.django_db
class TestCategorySeeding:
    """Tests for default category seeding service/command."""

    def test_default_categories_seeded_list(self):
        """Default category seeding creates all 10 required product categories."""
        assert Category is not None, "Category model is missing."
        run_category_seeding()

        for expected_name in DEFAULT_CATEGORY_NAMES:
            category = Category.objects.filter(name__iexact=expected_name).first()
            assert category is not None, f"Expected category '{expected_name}' was not seeded."
            assert category.urdu_name, f"Seeded category '{expected_name}' must have an Urdu name."
            assert category.color, f"Seeded category '{expected_name}' must have a color code."

    def test_default_categories_seeding_is_idempotent(self):
        """Running category seeding multiple times does not produce duplicate rows."""
        assert Category is not None, "Category model is missing."
        run_category_seeding()
        initial_count = Category.objects.count()

        # Run seeding a second time
        run_category_seeding()
        assert (
            Category.objects.count() == initial_count
        ), "Category seeding is not idempotent: duplicate records were created."


@pytest.mark.django_db
class TestCategoryViewsAndAccessControl:
    """Integration tests for category views and staff permission checks."""

    def _get_list_url(self):
        return resolve_candidate_url(
            ["/en/categories/", "/en/settings/categories/"],
            [("categories:category_list", None), ("categories:list", None)],
        )

    def _get_add_url(self):
        return resolve_candidate_url(
            ["/en/categories/add/", "/en/settings/categories/add/"],
            [("categories:category_add", None), ("categories:add", None)],
        )

    def _get_edit_url(self, pk):
        return resolve_candidate_url(
            [f"/en/categories/{pk}/edit/", f"/en/settings/categories/{pk}/edit/"],
            [("categories:category_edit", [pk]), ("categories:edit", [pk])],
        )

    def _get_archive_url(self, pk):
        return resolve_candidate_url(
            [
                f"/en/categories/{pk}/archive/",
                f"/en/categories/{pk}/toggle-archive/",
                f"/en/settings/categories/{pk}/archive/",
            ],
            [("categories:category_archive", [pk]), ("categories:archive", [pk])],
        )

    def test_unauthenticated_user_redirected(self, client):
        """Unauthenticated user accessing category endpoints is redirected to login."""
        list_url = self._get_list_url()
        response = client.get(list_url)
        assert response.status_code == 302
        assert "/login" in response.url or reverse("accounts:login") in response.url

    def test_superadmin_can_view_category_list(self, superadmin_client):
        """Superadmin can view the category management list."""
        category = create_sample_category()
        list_url = self._get_list_url()
        response = superadmin_client.get(list_url)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert category.name in content

    def test_superadmin_can_create_new_category(self, superadmin_client):
        """Superadmin can create a new category with name, urdu_name, and color hex."""
        assert Category is not None, "Category model is missing."
        add_url = self._get_add_url()
        post_data = {
            "name": "Stationery & Books",
            "urdu_name": "سٹیشنری اور کتب",
            "color": "#10B981",
        }
        response = superadmin_client.post(add_url, post_data)
        assert response.status_code in [200, 201, 302]

        created = Category.objects.filter(name="Stationery & Books").first()
        assert created is not None, "New category was not saved to database."
        assert created.urdu_name == "سٹیشنری اور کتب"
        assert created.color.upper() == "#10B981"

    def test_superadmin_can_edit_category(self, superadmin_client):
        """Superadmin can update category name and color."""
        category = create_sample_category()
        edit_url = self._get_edit_url(category.pk)
        post_data = {
            "name": "Updated Grocery Store",
            "urdu_name": "گروسری سٹور",
            "color": "#6366F1",
        }
        response = superadmin_client.post(edit_url, post_data)
        assert response.status_code in [200, 302]

        category.refresh_from_db()
        assert category.name == "Updated Grocery Store"
        assert category.color.upper() == "#6366F1"

    def test_superadmin_can_archive_category(self, superadmin_client):
        """Superadmin can toggle category is_archived state."""
        category = create_sample_category()
        assert category.is_archived is False
        archive_url = self._get_archive_url(category.pk)
        response = superadmin_client.post(archive_url)
        assert response.status_code in [200, 302]

        category.refresh_from_db()
        assert category.is_archived is True

    def test_staff_without_can_manage_categories_denied(self, staff_client):
        """Staff user without can_manage_categories is denied create/edit/archive actions."""
        category = create_sample_category()
        add_url = self._get_add_url()
        post_response = staff_client.post(add_url, {"name": "Unauthorized Cat", "color": "#123456"})
        assert post_response.status_code in [403, 302]

        edit_url = self._get_edit_url(category.pk)
        edit_response = staff_client.post(edit_url, {"name": "Hacked Name", "color": "#123456"})
        assert edit_response.status_code in [403, 302]
        category.refresh_from_db()
        assert category.name != "Hacked Name"

    def test_staff_with_can_manage_categories_permitted(self, client):
        """Staff user with can_manage_categories=True can successfully create categories."""
        assert Category is not None, "Category model is missing."
        staff_user = create_staff_with_category_permission()
        client.force_login(staff_user)

        add_url = self._get_add_url()
        post_data = {
            "name": "Hardware Supplies",
            "urdu_name": "ہارڈویئر سامان",
            "color": "#F59E0B",
        }
        response = client.post(add_url, post_data)
        assert response.status_code in [200, 201, 302]

        assert Category.objects.filter(name="Hardware Supplies").exists()


@pytest.mark.django_db
class TestUnitModelAndSeeding:
    """Unit tests for the Unit model and standard measurement units seeding."""

    def test_unit_model_exists(self):
        """Unit model must be implemented in categories.models."""
        assert Unit is not None, "Unit model is not implemented in categories.models."

    def test_create_custom_unit(self):
        """Custom Unit can be created with name, code, and urdu_name."""
        assert Unit is not None, "Unit model is missing."
        unit = Unit.objects.create(
            name="Bundle",
            code="bdl",
            urdu_name="بنڈل",
        )
        assert unit.pk is not None
        refreshed = Unit.objects.get(pk=unit.pk)
        assert refreshed.name == "Bundle"
        assert refreshed.code == "bdl"
        assert refreshed.urdu_name == "بنڈل"

    def test_unit_unique_code_constraint(self):
        """Duplicate unit codes must be rejected."""
        assert Unit is not None, "Unit model is missing."
        Unit.objects.create(name="Kilogram", code="kg", urdu_name="کلو")
        with pytest.raises((IntegrityError, ValidationError)):
            dup = Unit(name="Kilo Duplicate", code="kg", urdu_name="کلو")
            dup.full_clean()
            dup.save()

    def test_unit_str_representation(self):
        """str(Unit) should return unit name or code."""
        assert Unit is not None, "Unit model is missing."
        unit = Unit.objects.create(name="Liter", code="ltr", urdu_name="لیٹر")
        assert "ltr" in str(unit).lower() or "liter" in str(unit).lower()

    def test_standard_units_seeded_list(self):
        """Standard units seeding creates all required measurement units."""
        assert Unit is not None, "Unit model is missing."
        run_unit_seeding()

        for expected_code in STANDARD_UNIT_CODES:
            unit = Unit.objects.filter(code__iexact=expected_code).first()
            assert unit is not None, f"Standard unit with code '{expected_code}' was not seeded."
            assert unit.name, f"Seeded unit '{expected_code}' must have an English name."
            assert unit.urdu_name, f"Seeded unit '{expected_code}' must have an Urdu name."

    def test_standard_units_seeding_is_idempotent(self):
        """Running unit seeding multiple times does not create duplicates."""
        assert Unit is not None, "Unit model is missing."
        run_unit_seeding()
        initial_count = Unit.objects.count()

        run_unit_seeding()
        assert (
            Unit.objects.count() == initial_count
        ), "Unit seeding is not idempotent: duplicate records were created."


@pytest.mark.django_db
class TestUnitViewsAndPermissions:
    """Integration tests for unit management views and permissions."""

    def _get_units_url(self):
        return resolve_candidate_url(
            ["/en/settings/units/", "/en/categories/units/", "/en/units/"],
            [("categories:unit_list", None), ("categories:units", None)],
        )

    def _get_unit_add_url(self):
        return resolve_candidate_url(
            [
                "/en/settings/units/add/",
                "/en/categories/units/add/",
                "/en/units/add/",
            ],
            [("categories:unit_add", None), ("categories:add_unit", None)],
        )

    def test_superadmin_can_view_units_list(self, superadmin_client):
        """Superadmin can view the units listing."""
        url = self._get_units_url()
        response = superadmin_client.get(url)
        assert response.status_code == 200

    def test_superadmin_can_add_custom_unit(self, superadmin_client):
        """Superadmin can add a new custom measurement unit."""
        assert Unit is not None, "Unit model is missing."
        add_url = self._get_unit_add_url()
        post_data = {
            "name": "Carton Box",
            "code": "ctn",
            "urdu_name": "کارٹن",
        }
        response = superadmin_client.post(add_url, post_data)
        assert response.status_code in [200, 201, 302]

        created = Unit.objects.filter(code="ctn").first()
        assert created is not None, "Custom unit was not created in database."
        assert created.name == "Carton Box"

    def test_staff_without_permission_cannot_add_unit(self, staff_client, superadmin_client):
        """Staff without can_manage_categories cannot add custom units."""
        add_url = self._get_unit_add_url()
        # Verify unit management route is mounted
        list_url = self._get_units_url()
        assert superadmin_client.get(list_url).status_code == 200, "Units views not implemented"

        response = staff_client.post(
            add_url,
            {"name": "Unauthorized Unit", "code": "unauth", "urdu_name": "غیر مجاز"},
        )
        assert response.status_code in [403, 302]
        if Unit is not None:
            assert not Unit.objects.filter(code="unauth").exists()

    def test_staff_with_permission_can_add_custom_unit(self, client):
        """Staff with can_manage_categories=True can add custom units."""
        assert Unit is not None, "Unit model is missing."
        staff_user = create_staff_with_category_permission()
        client.force_login(staff_user)
        add_url = self._get_unit_add_url()
        post_data = {
            "name": "Packet",
            "code": "pkt",
            "urdu_name": "پیکٹ",
        }
        response = client.post(add_url, post_data)
        assert response.status_code in [200, 201, 302]
        assert Unit.objects.filter(code="pkt").exists()
