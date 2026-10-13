"""
tests/conftest.py
==================
Shared pytest fixtures for the aibilling test suite.

These fixtures are available in every test file automatically.
No need to import them — pytest finds them here.

Usage in a test:
    def test_superadmin_can_view_users(superadmin_user, client):
        client.force_login(superadmin_user)
        response = client.get("/en/admin/")
        assert response.status_code == 200
"""

import sys

import pytest
from django.contrib.auth import get_user_model
from django.template.context import BaseContext

# Python 3.14 + Django 4.2 compatibility:
# In Python 3.14, copy(super()) inside BaseContext.__copy__ does not copy
# instance attributes (__dict__) correctly, causing template rendering errors.
if sys.version_info >= (3, 14):

    def _patched_base_context_copy(self):
        duplicate = object.__new__(self.__class__)
        duplicate.__dict__.update(self.__dict__)
        duplicate.dicts = self.dicts[:]
        return duplicate

    BaseContext.__copy__ = _patched_base_context_copy

User = get_user_model()


@pytest.fixture(autouse=True)
def reset_translation():
    """Ensure every test starts and ends with English active, preventing locale leakage."""
    from django.utils import translation

    translation.activate("en")
    yield
    translation.activate("en")


@pytest.fixture
def superadmin_user(db):
    """Create and return a superadmin user for testing.

    The user has:
    - username: "superadmin"
    - password: "TestPass123!"
    - role: superadmin
    - is_staff: True (required for Django admin access)
    - is_superuser: True (full permissions)
    """
    return User.objects.create_user(
        username="superadmin",
        email="superadmin@example.com",
        password="TestPass123!",
        role=User.Role.SUPERADMIN,
        is_staff=True,
        is_superuser=True,
        first_name="Super",
        last_name="Admin",
    )


@pytest.fixture
def staff_user(db):
    """Create and return a staff user for testing.

    The user has:
    - username: "staffuser"
    - password: "TestPass123!"
    - role: staff
    - No admin or superuser privileges
    """
    return User.objects.create_user(
        username="staffuser",
        email="staff@example.com",
        password="TestPass123!",
        role=User.Role.STAFF,
        is_staff=False,
        is_superuser=False,
        first_name="Staff",
        last_name="User",
    )


@pytest.fixture
def superadmin_client(superadmin_user):
    """Return a test client already logged in as superadmin."""
    from django.test import Client

    c = Client()
    c.force_login(superadmin_user)
    return c


@pytest.fixture
def staff_client(staff_user):
    """Return a test client already logged in as a staff member."""
    from django.test import Client

    c = Client()
    c.force_login(staff_user)
    return c
