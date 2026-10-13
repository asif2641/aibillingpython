"""
sync/services.py
================
Offline synchronization business logic and queue processing services.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from billing.utils import money_round
from bills.models import Bill, BillItem
from bills.services import recalculate_bill_totals
from categories.models import Category, Unit
from ledger.services import record_payment
from parties.models import Party
from parties.services import match_or_create_party
from sync.models import SyncQueue


def _parse_date_safe(val: Any) -> date:
    """Parse date safely from string, datetime, or date, defaulting to today.

    Args:
        val: The value to parse into a date.

    Returns:
        datetime.date instance.
    """
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str) and val.strip():
        cleaned = val.strip()
        parsed = parse_date(cleaned)
        if parsed:
            return parsed
        parsed_dt = parse_datetime(cleaned)
        if parsed_dt:
            return parsed_dt.date()
        if "/" in cleaned:
            parts = cleaned.split("/")
            if len(parts) == 3:
                try:
                    d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                    if y < 100:
                        y += 2000
                    return date(y, m, d)
                except (ValueError, TypeError):
                    pass
    return timezone.now().date()


def _parse_datetime_safe(val: Any) -> datetime | None:
    """Parse a datetime safely and ensure timezone awareness.

    Args:
        val: The value to parse into a datetime.

    Returns:
        Timezone-aware datetime or None if invalid/unparseable.
    """
    if isinstance(val, datetime):
        if timezone.is_naive(val):
            return timezone.make_aware(val)
        return val
    if isinstance(val, date):
        dt = datetime.combine(val, datetime.min.time())
        return timezone.make_aware(dt)
    if isinstance(val, str) and val.strip():
        cleaned = val.strip()
        dt = parse_datetime(cleaned)
        if dt:
            if timezone.is_naive(dt):
                return timezone.make_aware(dt)
            return dt
        d = parse_date(cleaned)
        if d:
            dt = datetime.combine(d, datetime.min.time())
            return timezone.make_aware(dt)
    return None


def process_sync_queue_item(
    queue_item: SyncQueue,
    user: Any = None,
) -> tuple[bool, str, int | None]:
    """Process a single item from the sync queue.

    Extracts payload, matches or creates the party, checks for duplicate
    invoices for idempotency, creates the Bill and BillItem records,
    recalculates totals, and records initial payments.

    Args:
        queue_item: The SyncQueue model instance to process.
        user: Optional user instance to associate with the bill / queue item.

    Returns:
        tuple of (success: bool, message: str, resolved_record_id: int | None).
    """
    # Idempotency guard: if already processed and resolved, return immediately
    if queue_item.status == SyncQueue.Status.PROCESSED and queue_item.resolved_record_id:
        return True, "Already processed", queue_item.resolved_record_id

    if user and not queue_item.user:
        queue_item.user = user

    try:
        if queue_item.record_type != SyncQueue.RecordType.BILL:
            raise ValidationError(f"Unsupported record type: {queue_item.record_type}")

        payload = queue_item.payload or {}
        if not isinstance(payload, dict):
            raise ValidationError("Payload must be a dictionary")

        invoice_no = str(payload.get("invoice_no") or "").strip()
        bill_date = _parse_date_safe(payload.get("bill_date"))

        bill_type = payload.get("bill_type", "purchase")
        if bill_type not in (Bill.BillType.PURCHASE, Bill.BillType.SALE):
            bill_type = Bill.BillType.PURCHASE

        party_id = payload.get("party_id")
        party_name = str(payload.get("party_name") or "").strip()
        party_phone = str(payload.get("party_phone") or "").strip()
        party_urdu_name = str(
            payload.get("urdu_name") or payload.get("party_urdu_name") or ""
        ).strip()

        # Match or resolve Party
        party: Party | None = None
        if party_id:
            try:
                party = Party.objects.get(pk=party_id)
            except (Party.DoesNotExist, ValueError):
                party = None

        if party is None:
            if party_name:
                party = match_or_create_party(
                    name=party_name,
                    phone=party_phone or None,
                    party_type="vendor" if bill_type == "purchase" else "customer",
                    urdu_name=party_urdu_name,
                )
            else:
                raise ValidationError("Party name or party_id is required")

        # Check duplicate invoice / idempotency
        if invoice_no:
            existing_bill = Bill.objects.filter(
                is_deleted=False,
                party=party,
                invoice_no=invoice_no,
                bill_date=bill_date,
            ).first()
            if existing_bill:
                queue_item.status = SyncQueue.Status.PROCESSED
                queue_item.resolved_record_id = existing_bill.pk
                queue_item.processed_at = timezone.now()
                queue_item.error_message = ""
                if queue_item.pk:
                    queue_item.save(
                        update_fields=[
                            "status",
                            "resolved_record_id",
                            "processed_at",
                            "error_message",
                        ]
                    )
                else:
                    queue_item.save()
                return True, "Bill already exists (duplicate avoided)", existing_bill.pk

        category_id = payload.get("category_id")
        category = None
        if category_id:
            category = Category.objects.filter(pk=category_id).first()

        items = payload.get("items")
        if not items or not isinstance(items, list) or len(items) == 0:
            raise ValidationError("Bill must contain at least one line item")

        raw_discount = payload.get("discount", 0)
        try:
            discount = (
                money_round(Decimal(str(raw_discount)))
                if raw_discount is not None
                else Decimal("0.00")
            )
        except (ValueError, TypeError, InvalidOperation):
            discount = Decimal("0.00")

        raw_tax = payload.get("tax", 0)
        try:
            tax = money_round(Decimal(str(raw_tax))) if raw_tax is not None else Decimal("0.00")
        except (ValueError, TypeError, InvalidOperation):
            tax = Decimal("0.00")

        raw_amount_paid = payload.get("amount_paid", 0)
        try:
            amount_paid = (
                money_round(Decimal(str(raw_amount_paid)))
                if raw_amount_paid is not None
                else Decimal("0.00")
            )
        except (ValueError, TypeError, InvalidOperation):
            amount_paid = Decimal("0.00")

        notes = str(payload.get("notes") or "").strip()

        with transaction.atomic():
            bill = Bill.objects.create(
                bill_type=bill_type,
                party=party,
                category=category,
                invoice_no=invoice_no or "",
                bill_date=bill_date,
                source=Bill.Source.MANUAL,
                status=Bill.Status.VERIFIED,
                created_by=queue_item.user or user,
                notes=notes,
                subtotal=Decimal("0.00"),
                discount=Decimal("0.00"),
                tax=Decimal("0.00"),
                grand_total=Decimal("0.00"),
                amount_paid=Decimal("0.00"),
            )

            for idx, item in enumerate(items):
                try:
                    quantity = Decimal(str(item.get("quantity", 1)))
                    unit_price = Decimal(str(item.get("unit_price", 0)))
                except (ValueError, TypeError, InvalidOperation) as err:
                    raise ValidationError("Quantity and unit price must be positive") from err

                if quantity <= Decimal("0") or unit_price < Decimal("0"):
                    raise ValidationError("Quantity and unit price must be positive")

                name = item.get("name") or item.get("item_name", "Item") or "Item"
                urdu_item_name = str(
                    item.get("urdu_item_name") or item.get("urdu_name") or ""
                ).strip()
                unit = item.get("unit", "") or ""
                line_total = money_round(quantity * unit_price)

                BillItem.objects.create(
                    bill=bill,
                    serial_no=idx + 1,
                    item_name=str(name).strip(),
                    urdu_item_name=urdu_item_name,
                    unit=str(unit).strip(),
                    quantity=quantity,
                    unit_price=unit_price,
                    line_total=line_total,
                )

            bill.discount = discount
            bill.tax = tax
            bill.save(update_fields=["discount", "tax"])
            recalculate_bill_totals(bill)

            if amount_paid > Decimal("0.00"):
                record_payment(
                    party=party,
                    amount=amount_paid,
                    bill=bill,
                    payment_date=bill_date,
                    payment_method="cash",
                    notes="Synced offline payment",
                    created_by=queue_item.user or user,
                )

            queue_item.status = SyncQueue.Status.PROCESSED
            queue_item.resolved_record_id = bill.pk
            queue_item.processed_at = timezone.now()
            queue_item.error_message = ""
            if queue_item.pk:
                queue_item.save(
                    update_fields=[
                        "status",
                        "resolved_record_id",
                        "processed_at",
                        "error_message",
                    ]
                )
            else:
                queue_item.save()

        return True, "Bill synced successfully", bill.pk

    except Exception as e:
        queue_item.status = SyncQueue.Status.FAILED
        queue_item.error_message = str(e)
        queue_item.retry_count += 1
        if queue_item.pk:
            queue_item.save(update_fields=["status", "error_message", "retry_count"])
        else:
            queue_item.save()
        return False, str(e), None


def sync_push_service(user: Any, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Process a batch of offline sync queue items pushed by a client.

    Args:
        user: The authenticated user pushing the items.
        items: List of dictionary records from client queue.

    Returns:
        dict with success status, processed list, failed list, and total count.
    """
    processed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    if not isinstance(items, list):
        return {
            "success": False,
            "processed": [],
            "failed": [],
            "total": 0,
        }

    for item in items:
        if not isinstance(item, dict):
            continue

        client_id = item.get("client_id")
        if not client_id:
            continue

        raw_client_ts = item.get("client_timestamp")
        client_timestamp = _parse_datetime_safe(raw_client_ts) if raw_client_ts else None

        queue_item, created = SyncQueue.objects.get_or_create(
            client_id=str(client_id).strip(),
            defaults={
                "user": user,
                "record_type": item.get("record_type", SyncQueue.RecordType.BILL),
                "action": item.get("action", SyncQueue.Action.CREATE),
                "payload": item.get("payload", {}),
                "client_timestamp": client_timestamp,
            },
        )

        if not created and queue_item.status != SyncQueue.Status.PROCESSED:
            update_fields: list[str] = []
            if user and not queue_item.user:
                queue_item.user = user
                update_fields.append("user")
            if "payload" in item and item["payload"] != queue_item.payload:
                queue_item.payload = item["payload"]
                update_fields.append("payload")
            if update_fields:
                queue_item.save(update_fields=update_fields)

        if queue_item.status == SyncQueue.Status.PROCESSED and queue_item.resolved_record_id:
            processed.append(
                {
                    "client_id": queue_item.client_id,
                    "record_id": queue_item.resolved_record_id,
                    "status": "processed",
                    "message": "Already processed",
                }
            )
        else:
            success, message, record_id = process_sync_queue_item(queue_item, user=user)
            if success:
                processed.append(
                    {
                        "client_id": queue_item.client_id,
                        "record_id": record_id,
                        "status": "processed",
                        "message": message,
                    }
                )
            else:
                failed.append(
                    {
                        "client_id": queue_item.client_id,
                        "error": message,
                        "status": "failed",
                    }
                )

    return {
        "success": True,
        "processed": processed,
        "failed": failed,
        "total": len(items),
    }


def sync_pull_service(user: Any = None, since: Any = None) -> dict[str, Any]:
    """Pull reference data (parties, categories, units) for offline PWA caching.

    Args:
        user: The requesting user (optional).
        since: Optional timestamp (datetime or ISO string) to fetch delta updates.

    Returns:
        dict containing parties, categories, units, and server_time.
    """
    parties_qs = Party.objects.filter(is_active=True).order_by("name")
    categories_qs = Category.objects.filter(is_archived=False).order_by("name")
    units_qs = Unit.objects.all().order_by("name")

    if since is not None:
        since_dt = _parse_datetime_safe(since)
        if since_dt is not None:
            parties_qs = parties_qs.filter(updated_at__gte=since_dt)
            categories_qs = categories_qs.filter(updated_at__gte=since_dt)

    parties = [
        {
            "id": p.id,
            "name": p.name,
            "urdu_name": p.urdu_name or "",
            "party_type": p.party_type,
            "phone": p.phone or "",
        }
        for p in parties_qs
    ]

    categories = [
        {
            "id": c.id,
            "name": c.name,
            "urdu_name": c.urdu_name or "",
            "color": c.color or "#3B82F6",
        }
        for c in categories_qs
    ]

    units = [
        {
            "id": u.id,
            "name": u.name,
            "code": u.code,
            "urdu_name": u.urdu_name or "",
        }
        for u in units_qs
    ]

    return {
        "parties": parties,
        "categories": categories,
        "units": units,
        "server_time": timezone.now().isoformat(),
    }
