"""
settings_app/signals.py
=======================
Signal receivers for automatic ActivityLog audit entries and dashboard cache invalidation.
"""

from __future__ import annotations

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from bills.models import Bill
from ledger.models import Payment
from parties.models import Party
from settings_app.services import log_activity

DASHBOARD_CACHE_KEY = "dashboard_summary_data"


def invalidate_dashboard_cache() -> None:
    """Clear cached dashboard KPIs and chart data."""
    cache.delete(DASHBOARD_CACHE_KEY)


@receiver(pre_save, sender=Bill)
def capture_bill_pre_save_state(sender, instance: Bill, **kwargs) -> None:
    """Store previous is_deleted state on the instance before saving."""
    if instance.pk:
        prev = Bill.all_objects.filter(pk=instance.pk).values_list("is_deleted", flat=True).first()
        instance._prev_is_deleted = prev
    else:
        instance._prev_is_deleted = None


@receiver(post_save, sender=Bill)
def handle_bill_post_save(sender, instance: Bill, created: bool, **kwargs) -> None:
    """Log bill lifecycle events and invalidate dashboard cache."""
    invalidate_dashboard_cache()

    inv_label = instance.invoice_no or f"#{instance.pk}"
    if created:
        log_activity(
            user=instance.created_by,
            action="bill_created",
            target_type="Bill",
            target_id=instance.pk,
            description=f"Created bill {inv_label}",
        )
        return

    prev_deleted = getattr(instance, "_prev_is_deleted", None)
    if prev_deleted is False and instance.is_deleted is True:
        log_activity(
            user=instance.created_by,
            action="bill_deleted",
            target_type="Bill",
            target_id=instance.pk,
            description=f"Moved bill {inv_label} to trash",
        )
    elif prev_deleted is True and instance.is_deleted is False:
        log_activity(
            user=instance.created_by,
            action="bill_restored",
            target_type="Bill",
            target_id=instance.pk,
            description=f"Restored bill {inv_label} from trash",
        )
    else:
        log_activity(
            user=instance.created_by,
            action="bill_updated",
            target_type="Bill",
            target_id=instance.pk,
            description=f"Updated bill {inv_label}",
        )


@receiver(post_delete, sender=Bill)
def handle_bill_post_delete(sender, instance: Bill, **kwargs) -> None:
    """Invalidate dashboard cache when a bill is permanently deleted."""
    invalidate_dashboard_cache()


@receiver(post_save, sender=Payment)
def handle_payment_post_save(sender, instance: Payment, created: bool, **kwargs) -> None:
    """Log payment recording and invalidate dashboard cache."""
    invalidate_dashboard_cache()

    if created:
        party_name = instance.party.name if instance.party_id else ""
        log_activity(
            user=instance.created_by,
            action="payment_recorded",
            target_type="Payment",
            target_id=instance.pk,
            description=f"Recorded payment of {instance.amount} for {party_name}".strip(),
        )


@receiver(post_delete, sender=Payment)
def handle_payment_post_delete(sender, instance: Payment, **kwargs) -> None:
    """Invalidate dashboard cache when a payment is deleted."""
    invalidate_dashboard_cache()


@receiver(post_save, sender=Party)
def handle_party_post_save(sender, instance: Party, created: bool, **kwargs) -> None:
    """Log new party creation."""
    if created:
        log_activity(
            user=None,
            action="party_created",
            target_type="Party",
            target_id=instance.pk,
            description=f"Created party {instance.name}",
        )
