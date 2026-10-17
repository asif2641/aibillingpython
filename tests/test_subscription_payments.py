"""tests/test_subscription_payments.py
======================================
Tests for Phase 1 Subscription Payment Submission & Superadmin Verification Workflow.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import SubscriptionPaymentRequest

User = get_user_model()


@pytest.fixture
def superadmin_user(db):
    return User.objects.create_superuser(
        username="admin_super",
        email="super@scanbooks.local",
        password="SuperPass123!",
    )


@pytest.fixture
def tenant_user(db):
    return User.objects.create_user(
        username="shop_owner",
        email="owner@store.local",
        password="OwnerPass123!",
        role=User.Role.STAFF,
        plan=User.Plan.FREE,
        monthly_scan_quota=10,
        business_name="Al-Madina Store",
    )


@pytest.mark.django_db
class TestSubscriptionPaymentFlow:
    """Test tenant payment proof submission and superadmin approval/rejection."""

    def test_tenant_submits_upgrade_payment_request(self, client, tenant_user):
        """Happy path: tenant submits payment proof for Pro plan upgrade."""
        client.force_login(tenant_user)

        response = client.post(
            reverse("accounts:subscription"),
            data={
                "plan": "pro",
                "amount": "1500.00",
                "payment_method": "jazzcash",
                "transaction_id": "TID-9921448",
                "customer_notes": "Paid from Ali Raza account",
            },
        )
        assert response.status_code == 302
        assert response.url == reverse("accounts:subscription")

        # Verify request created with pending status
        payment_req = SubscriptionPaymentRequest.objects.filter(user=tenant_user).first()
        assert payment_req is not None
        assert payment_req.plan == "pro"
        assert payment_req.amount == Decimal("1500.00")
        assert payment_req.payment_method == "jazzcash"
        assert payment_req.transaction_id == "TID-9921448"
        assert payment_req.status == SubscriptionPaymentRequest.Status.PENDING

        # Tenant's plan remains Free until admin approves
        tenant_user.refresh_from_db()
        assert tenant_user.plan == User.Plan.FREE
        assert tenant_user.monthly_scan_quota == 10

    def test_superadmin_approves_payment_request(self, client, superadmin_user, tenant_user):
        """Superadmin approves payment request and upgrades tenant to Pro."""
        payment_req = SubscriptionPaymentRequest.objects.create(
            user=tenant_user,
            plan="pro",
            amount=Decimal("1500.00"),
            payment_method="bank_transfer",
            transaction_id="RAAST-882199",
            status=SubscriptionPaymentRequest.Status.PENDING,
        )

        client.force_login(superadmin_user)
        response = client.post(
            reverse("accounts:superadmin_approve_payment_request", args=[payment_req.id])
        )
        assert response.status_code == 302
        assert response.url == reverse("accounts:superadmin_dashboard")

        # Verify request updated
        payment_req.refresh_from_db()
        assert payment_req.status == SubscriptionPaymentRequest.Status.APPROVED
        assert payment_req.reviewed_by == superadmin_user
        assert payment_req.reviewed_at is not None

        # Verify tenant upgraded
        tenant_user.refresh_from_db()
        assert tenant_user.plan == User.Plan.PRO
        assert tenant_user.monthly_scan_quota in (100, 150)

    def test_superadmin_approves_business_tier_request(self, client, superadmin_user, tenant_user):
        """Superadmin approves business tier request and sets quota to 500 scans."""
        payment_req = SubscriptionPaymentRequest.objects.create(
            user=tenant_user,
            plan="business",
            amount=Decimal("4000.00"),
            payment_method="bank_transfer",
            transaction_id="TX-5500",
            status=SubscriptionPaymentRequest.Status.PENDING,
        )

        client.force_login(superadmin_user)
        client.post(reverse("accounts:superadmin_approve_payment_request", args=[payment_req.id]))

        tenant_user.refresh_from_db()
        assert tenant_user.plan == User.Plan.BUSINESS
        assert tenant_user.monthly_scan_quota == 500

    def test_superadmin_rejects_payment_request(self, client, superadmin_user, tenant_user):
        """Superadmin rejects payment request with note, tenant plan remains unchanged."""
        payment_req = SubscriptionPaymentRequest.objects.create(
            user=tenant_user,
            plan="pro",
            amount=Decimal("1500.00"),
            payment_method="jazzcash",
            transaction_id="INVALID-TID",
            status=SubscriptionPaymentRequest.Status.PENDING,
        )

        client.force_login(superadmin_user)
        response = client.post(
            reverse("accounts:superadmin_reject_payment_request", args=[payment_req.id]),
            data={"admin_notes": "TID not found in JazzCash statement"},
        )
        assert response.status_code == 302

        payment_req.refresh_from_db()
        assert payment_req.status == SubscriptionPaymentRequest.Status.REJECTED
        assert payment_req.admin_notes == "TID not found in JazzCash statement"

        # Tenant stays on free
        tenant_user.refresh_from_db()
        assert tenant_user.plan == User.Plan.FREE

    def test_tenant_downgrades_to_free_immediately(self, client, tenant_user):
        """Tenant on Pro can downgrade back to Free directly without approval."""
        tenant_user.plan = User.Plan.PRO
        tenant_user.monthly_scan_quota = 100
        tenant_user.save()

        client.force_login(tenant_user)
        response = client.post(
            reverse("accounts:subscription"),
            data={"action": "downgrade_free"},
        )
        assert response.status_code == 302

        tenant_user.refresh_from_db()
        assert tenant_user.plan == User.Plan.FREE
        assert tenant_user.monthly_scan_quota == 10

    def test_non_superadmin_cannot_approve_payment_requests(self, client, tenant_user):
        """Ordinary tenant cannot approve payment requests (security check 403)."""
        payment_req = SubscriptionPaymentRequest.objects.create(
            user=tenant_user,
            plan="pro",
            amount=Decimal("1500.00"),
            payment_method="bank_transfer",
            transaction_id="TX-123",
        )

        client.force_login(tenant_user)
        response = client.post(
            reverse("accounts:superadmin_approve_payment_request", args=[payment_req.id])
        )
        assert response.status_code == 403

    def test_subscription_page_renders_pending_banner(self, client, tenant_user):
        """Subscription page displays pending review banner when request exists."""
        SubscriptionPaymentRequest.objects.create(
            user=tenant_user,
            plan="pro",
            amount=Decimal("1500.00"),
            payment_method="jazzcash",
            transaction_id="TID-BANNER-TEST",
            status=SubscriptionPaymentRequest.Status.PENDING,
        )

        client.force_login(tenant_user)
        response = client.get(reverse("accounts:subscription"))
        assert response.status_code == 200
        assert (
            b"Upgrade Request Pending Review: Pro" in response.content
            or b"TID-BANNER-TEST" in response.content
        )
