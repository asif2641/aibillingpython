"""tests/test_superadmin_dashboard.py
===================================
Tests for the dedicated Frontend Super Admin SaaS Management Dashboard.

Coverage:
- Access Control:
  - Superadmin user (is_superuser=True) gets HTTP 200 at /en/accounts/superadmin/.
  - Regular tenant / non-superuser gets HTTP 403 Forbidden.
  - Unauthenticated visitor is redirected to login.
- Metrics & KPIs:
  - Total tenant count.
  - Estimated MRR calculation based on active Pro and Business tiers.
  - Total platform AI scans and bills processed.
- Tenant Management Actions:
  - Search tenants by username, email, and business name.
  - Filter tenants by subscription plan (free, pro, business).
  - Update tenant subscription plan and scan quota via POST.
  - Toggle tenant account active status (activate/suspend).
  - Add bonus scans to tenant's quota.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.fixture
def sample_tenants(db):
    """Create sample tenant accounts with varying plans and scan usage."""
    t1 = User.objects.create_user(
        username="lahore_mart",
        email="owner@lahoremart.pk",
        password="Password123!",
        business_name="Lahore Super Mart",
        plan=User.Plan.FREE,
        monthly_scan_quota=10,
        scans_used_this_month=4,
        is_superuser=False,
        is_staff=False,
    )
    t2 = User.objects.create_user(
        username="karachi_wholesale",
        email="contact@kwholesalers.pk",
        password="Password123!",
        business_name="Karachi Wholesalers",
        plan=User.Plan.PRO,
        monthly_scan_quota=100,
        scans_used_this_month=45,
        is_superuser=False,
        is_staff=False,
    )
    t3 = User.objects.create_user(
        username="islamabad_distrib",
        email="info@isbdistrib.pk",
        password="Password123!",
        business_name="Islamabad Distributors",
        plan=User.Plan.BUSINESS,
        monthly_scan_quota=500,
        scans_used_this_month=120,
        is_superuser=False,
        is_staff=False,
    )
    return [t1, t2, t3]


@pytest.mark.django_db
class TestSuperadminDashboardAccess:
    """Verify security boundaries and role access controls."""

    def test_superadmin_can_access_dashboard(self, superadmin_client, sample_tenants):
        """Super Admin user has full access to the SaaS management dashboard."""
        url = reverse("accounts:superadmin_dashboard")
        response = superadmin_client.get(url)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "SaaS" in content or "Admin" in content
        assert "Lahore Super Mart" in content
        assert "Karachi Wholesalers" in content
        assert "Islamabad Distributors" in content

    def test_regular_tenant_forbidden_from_superadmin_dashboard(self, staff_client):
        """Non-superuser (tenant or staff) gets HTTP 403 Forbidden."""
        url = reverse("accounts:superadmin_dashboard")
        response = staff_client.get(url)
        assert response.status_code == 403

    def test_unauthenticated_user_redirected_to_login(self, client):
        """Anonymous visitor is redirected to the login page."""
        url = reverse("accounts:superadmin_dashboard")
        response = client.get(url)
        assert response.status_code == 302
        assert "/accounts/login/" in response.url


@pytest.mark.django_db
class TestSuperadminMetricsAndFilters:
    """Verify financial KPIs, metrics aggregation, and table filtering."""

    def test_metrics_and_mrr_calculation(self, superadmin_client, sample_tenants):
        """Dashboard renders accurate MRR based on active Pro and Business subscribers."""
        url = reverse("accounts:superadmin_dashboard")
        response = superadmin_client.get(url)
        assert response.status_code == 200
        # MRR calculation: 1 Pro (1,500) + 1 Business (4,000) = 5,500 PKR
        assert response.context["total_tenants"] >= 3
        assert response.context["pro_count"] >= 1
        assert response.context["business_count"] >= 1
        assert response.context["estimated_mrr"] >= Decimal("5500.00")

    def test_search_tenants_by_query(self, superadmin_client, sample_tenants):
        """Searching by business name filters the displayed tenants."""
        url = reverse("accounts:superadmin_dashboard")
        response = superadmin_client.get(f"{url}?q=Karachi")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Karachi Wholesalers" in content
        assert "Lahore Super Mart" not in content

    def test_filter_tenants_by_plan(self, superadmin_client, sample_tenants):
        """Filtering by subscription tier displays only matching tenants."""
        url = reverse("accounts:superadmin_dashboard")
        response = superadmin_client.get(f"{url}?plan=pro")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Karachi Wholesalers" in content
        assert "Lahore Super Mart" not in content


@pytest.mark.django_db
class TestSuperadminTenantActions:
    """Verify modifying tenant subscriptions, quotas, and account status."""

    def test_superadmin_can_update_tenant_plan_and_quota(self, superadmin_client, sample_tenants):
        """Superadmin can upgrade a tenant to Pro or Business and set quota."""
        tenant = sample_tenants[0]  # Lahore Super Mart (initially Free)
        assert tenant.plan == User.Plan.FREE

        url = reverse("accounts:superadmin_update_tenant_plan", kwargs={"user_id": tenant.pk})
        post_data = {
            "plan": User.Plan.PRO,
            "monthly_scan_quota": 150,
        }
        response = superadmin_client.post(url, post_data)
        assert response.status_code == 302

        tenant.refresh_from_db()
        assert tenant.plan == User.Plan.PRO
        assert tenant.monthly_scan_quota == 150

    def test_superadmin_can_toggle_tenant_active_status(self, superadmin_client, sample_tenants):
        """Superadmin can suspend and reactivate a tenant account."""
        tenant = sample_tenants[1]
        assert tenant.is_active is True

        url = reverse("accounts:superadmin_toggle_tenant_status", kwargs={"user_id": tenant.pk})
        # Suspend
        resp1 = superadmin_client.post(url)
        assert resp1.status_code == 302
        tenant.refresh_from_db()
        assert tenant.is_active is False

        # Reactivate
        resp2 = superadmin_client.post(url)
        assert resp2.status_code == 302
        tenant.refresh_from_db()
        assert tenant.is_active is True

    def test_superadmin_can_add_bonus_scans(self, superadmin_client, sample_tenants):
        """Superadmin can grant immediate bonus scans to a tenant."""
        tenant = sample_tenants[0]
        initial_quota = tenant.monthly_scan_quota

        url = reverse("accounts:superadmin_add_bonus_scans", kwargs={"user_id": tenant.pk})
        response = superadmin_client.post(url, {"bonus_scans": 25})
        assert response.status_code == 302

        tenant.refresh_from_db()
        assert tenant.monthly_scan_quota == initial_quota + 25
