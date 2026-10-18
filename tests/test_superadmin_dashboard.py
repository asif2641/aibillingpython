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

from bills.models import Bill

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

    def test_superadmin_can_create_new_tenant(self, superadmin_client):
        """Superadmin can provision a new tenant directly from the console."""
        url = reverse("accounts:superadmin_create_tenant")
        post_data = {
            "business_name": "New Fresh Tenant Mart",
            "username": "fresh_tenant",
            "password": "Password123!",
            "email": "fresh@example.com",
            "plan": "pro",
            "monthly_scan_quota": 120,
        }
        response = superadmin_client.post(url, post_data)
        assert response.status_code == 302
        assert User.objects.filter(username="fresh_tenant").exists()
        created = User.objects.get(username="fresh_tenant")
        assert created.business_name == "New Fresh Tenant Mart"
        assert created.plan == User.Plan.PRO
        assert created.monthly_scan_quota == 120
        assert created.scans_used_this_month == 0
        assert created.check_password("Password123!")


@pytest.mark.django_db
class TestManualBillAndScanQuotaTracking:
    """Verify that manual bills are explicitly mentioned, broken down, and counted in monthly quota usage."""

    def test_tenant_with_scanned_and_manual_bills_shows_breakdown_and_effective_quota(
        self, superadmin_client
    ):
        """Happy path: 10 scans + 1 manual entry shows 11 bills, breakdown, and quota usage of 11."""
        from parties.models import Party

        tenant = User.objects.create_user(
            username="zz_ansari",
            email="zaid62390@gmail.com",
            business_name="ZZ ansari",
            plan=User.Plan.FREE,
            monthly_scan_quota=10,
            scans_used_this_month=10,
        )
        party = Party.objects.create(
            name="Vendor Ansari", party_type=Party.PartyType.VENDOR, user=tenant
        )

        for i in range(10):
            Bill.objects.create(
                created_by=tenant,
                party=party,
                invoice_no=f"SCAN-{i}",
                source=Bill.Source.SCAN,
                grand_total=Decimal("100.00"),
            )
        Bill.objects.create(
            created_by=tenant,
            party=party,
            invoice_no="MANUAL-1",
            source=Bill.Source.MANUAL,
            grand_total=Decimal("250.00"),
        )

        url = reverse("accounts:superadmin_dashboard")
        response = superadmin_client.get(url)
        assert response.status_code == 200

        content = response.content.decode("utf-8")
        assert "ZZ ansari" in content
        # Breakdown of scans and manual bills is present
        assert "10" in content
        assert "1" in content
        assert "11" in content

        tenants_in_ctx = response.context["tenants"]
        zz = next(t for t in tenants_in_ctx if t.username == "zz_ansari")
        assert zz.bills_count == 11
        assert zz.scanned_bills_count == 10
        assert zz.manual_bills_count == 1
        assert zz.effective_scans_used == 11
        assert zz.effective_remaining_scans == 0

    def test_tenant_with_only_manual_bills_counts_towards_quota(self, superadmin_client):
        """Edge case 1: Tenant with only manual entries has quota tracked accordingly."""
        from parties.models import Party

        tenant = User.objects.create_user(
            username="manual_only_shop",
            business_name="Manual Only Shop",
            plan=User.Plan.FREE,
            monthly_scan_quota=10,
            scans_used_this_month=0,
        )
        party = Party.objects.create(
            name="Manual Vendor", party_type=Party.PartyType.VENDOR, user=tenant
        )

        for i in range(3):
            Bill.objects.create(
                created_by=tenant,
                party=party,
                invoice_no=f"MAN-{i}",
                source=Bill.Source.MANUAL,
                grand_total=Decimal("50.00"),
            )

        url = reverse("accounts:superadmin_dashboard")
        response = superadmin_client.get(url)
        assert response.status_code == 200

        tenants_in_ctx = response.context["tenants"]
        t = next(t for t in tenants_in_ctx if t.username == "manual_only_shop")
        assert t.bills_count == 3
        assert t.scanned_bills_count == 0
        assert t.manual_bills_count == 3
        assert t.effective_scans_used == 3
        assert t.effective_remaining_scans == 7

    def test_tenant_with_only_scanned_bills(self, superadmin_client):
        """Edge case 2: Tenant with only scans displays breakdown cleanly."""
        from parties.models import Party

        tenant = User.objects.create_user(
            username="scans_only_shop",
            business_name="Scans Only Shop",
            plan=User.Plan.FREE,
            monthly_scan_quota=10,
            scans_used_this_month=5,
        )
        party = Party.objects.create(
            name="Scan Vendor", party_type=Party.PartyType.VENDOR, user=tenant
        )

        for i in range(5):
            Bill.objects.create(
                created_by=tenant,
                party=party,
                invoice_no=f"SC-{i}",
                source=Bill.Source.SCAN,
                grand_total=Decimal("50.00"),
            )

        url = reverse("accounts:superadmin_dashboard")
        response = superadmin_client.get(url)
        assert response.status_code == 200

        tenants_in_ctx = response.context["tenants"]
        t = next(t for t in tenants_in_ctx if t.username == "scans_only_shop")
        assert t.bills_count == 5
        assert t.scanned_bills_count == 5
        assert t.manual_bills_count == 0
        assert t.effective_scans_used == 5
        assert t.effective_remaining_scans == 5

    def test_manual_bill_creation_increments_quota_usage(self, client):
        """Edge case 3: Creating a manual bill increments tenant's monthly quota usage."""
        from parties.models import Party

        tenant = User.objects.create_user(
            username="shop_owner_1",
            password="Password123!",
            monthly_scan_quota=10,
            scans_used_this_month=2,
        )
        client.login(username="shop_owner_1", password="Password123!")

        vendor = Party.objects.create(
            name="Vendor A", party_type=Party.PartyType.VENDOR, user=tenant
        )

        url = reverse("bills:bill_add")
        post_data = {
            "bill_type": Bill.BillType.PURCHASE,
            "party": vendor.pk,
            "invoice_no": "INV-MAN-100",
            "bill_date": "2026-10-18",
            "status": Bill.Status.VERIFIED,
        }
        resp = client.post(url, post_data)
        assert resp.status_code == 302

        tenant.refresh_from_db()
        assert tenant.scans_used_this_month == 3
        created_bill = Bill.objects.get(invoice_no="INV-MAN-100")
        assert created_bill.source == Bill.Source.MANUAL

    def test_manual_bill_creation_blocked_when_quota_exhausted(self, client):
        """Failure case: Tenant at quota limit cannot create a manual bill and is redirected with error."""
        User.objects.create_user(
            username="quota_capped_user",
            password="Password123!",
            monthly_scan_quota=10,
            scans_used_this_month=10,
        )
        client.login(username="quota_capped_user", password="Password123!")

        url = reverse("bills:bill_add")
        resp = client.get(url)
        assert resp.status_code == 302
        assert reverse("accounts:subscription") in resp.url

        post_resp = client.post(url, {"invoice_no": "INV-CAPPED"})
        assert post_resp.status_code == 302
        assert reverse("accounts:subscription") in post_resp.url

    def test_offline_manual_bill_sync_increments_quota_usage(self):
        """Offline manual bill sync also consumes user quota."""
        from sync.models import SyncQueue
        from sync.services import process_sync_queue_item

        tenant = User.objects.create_user(
            username="offline_sync_user",
            monthly_scan_quota=10,
            scans_used_this_month=4,
        )
        queue_item = SyncQueue.objects.create(
            client_id="client-offline-999",
            user=tenant,
            action=SyncQueue.Action.CREATE,
            record_type=SyncQueue.RecordType.BILL,
            payload={
                "bill_type": "purchase",
                "party_name": "Offline Vendor",
                "invoice_no": "OFFLINE-999",
                "bill_date": "2026-10-18",
                "items": [{"name": "Milk", "quantity": 2, "unit_price": 100}],
            },
        )
        success, msg, bill_id = process_sync_queue_item(queue_item, user=tenant)
        assert success is True
        tenant.refresh_from_db()
        assert tenant.scans_used_this_month == 5
