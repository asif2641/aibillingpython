"""
settings_app/services.py
========================
Business logic for activity logging, database backups, and data exports.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import time
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from bills.models import Bill
from categories.models import Category, Unit
from ledger.models import Payment
from parties.models import Party
from settings_app.models import ActivityLog, ShopProfile


def log_activity(
    user=None,
    action: str = "",
    description: str = "",
    target_type: str = "",
    target_id: int | None = None,
    ip_address: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ActivityLog:
    """Record an audit activity log entry.

    Automatically normalizes AnonymousUser instances to None.
    """
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None

    return ActivityLog.objects.create(
        user=user,
        action=action,
        target_type=target_type,
        target_id=target_id,
        description=description,
        ip_address=ip_address,
        metadata=metadata or {},
    )


def generate_backup_payload() -> dict[str, Any]:
    """Export all non-sensitive shop data as a JSON-serializable dictionary.

    Never includes user password hashes, secret keys, or session tokens.
    """
    profile = ShopProfile.get_solo()
    shop_data = {
        "name": profile.name,
        "address": profile.address,
        "phone": profile.phone,
        "email": profile.email,
        "tax_number": profile.tax_number,
        "currency": profile.currency,
        "timezone": profile.timezone,
        "date_format": profile.date_format,
        "default_language": profile.default_language,
        "invoice_footer_text": profile.invoice_footer_text,
        "daily_scan_limit": profile.daily_scan_limit,
        "monthly_scan_limit": profile.monthly_scan_limit,
    }

    categories_data = [
        {
            "id": cat.id,
            "name": cat.name,
            "urdu_name": cat.urdu_name,
            "color": cat.color,
            "is_archived": cat.is_archived,
            "created_at": cat.created_at.isoformat() if cat.created_at else None,
        }
        for cat in Category.objects.all().order_by("id")
    ]

    units_data = [
        {
            "id": unit.id,
            "name": unit.name,
            "code": unit.code,
            "urdu_name": unit.urdu_name,
            "is_system": unit.is_system,
        }
        for unit in Unit.objects.all().order_by("id")
    ]

    parties_data = [
        {
            "id": party.id,
            "name": party.name,
            "urdu_name": party.urdu_name,
            "phone": party.phone,
            "email": party.email,
            "address": party.address,
            "tax_number": party.tax_number,
            "party_type": party.party_type,
            "notes": party.notes,
            "is_active": party.is_active,
            "created_at": party.created_at.isoformat() if party.created_at else None,
            "updated_at": party.updated_at.isoformat() if party.updated_at else None,
        }
        for party in Party.objects.all().order_by("id")
    ]

    bills_qs = (
        Bill.all_objects.select_related("party", "category")
        .prefetch_related("items")
        .order_by("id")
    )
    bills_data = []
    for bill in bills_qs:
        items_list = [
            {
                "id": item.id,
                "serial_no": item.serial_no,
                "item_name": item.item_name,
                "urdu_item_name": item.urdu_item_name,
                "quantity": str(item.quantity),
                "unit": item.unit,
                "unit_price": str(item.unit_price),
                "line_total": str(item.line_total),
            }
            for item in bill.items.all()
        ]
        bills_data.append(
            {
                "id": bill.id,
                "bill_type": bill.bill_type,
                "party_id": bill.party_id,
                "party_name": bill.party.name if bill.party else "",
                "invoice_no": bill.invoice_no,
                "bill_date": bill.bill_date.isoformat()
                if isinstance(bill.bill_date, (datetime.date, datetime.datetime))
                else str(bill.bill_date),
                "bill_time": bill.bill_time.isoformat() if bill.bill_time else None,
                "category_id": bill.category_id,
                "category_name": bill.category.name if bill.category else "",
                "status": bill.status,
                "source": bill.source,
                "subtotal": str(bill.subtotal),
                "discount": str(bill.discount),
                "tax": str(bill.tax),
                "grand_total": str(bill.grand_total),
                "payment_status": bill.payment_status,
                "amount_paid": str(bill.amount_paid),
                "notes": bill.notes,
                "is_deleted": bill.is_deleted,
                "deleted_at": bill.deleted_at.isoformat() if bill.deleted_at else None,
                "created_at": bill.created_at.isoformat() if bill.created_at else None,
                "updated_at": bill.updated_at.isoformat() if bill.updated_at else None,
                "items": items_list,
            }
        )

    payments_data = [
        {
            "id": pay.id,
            "party_id": pay.party_id,
            "party_name": pay.party.name if pay.party else "",
            "bill_id": pay.bill_id,
            "amount": str(pay.amount),
            "payment_date": pay.payment_date.isoformat()
            if isinstance(pay.payment_date, (datetime.date, datetime.datetime))
            else str(pay.payment_date),
            "payment_method": pay.payment_method,
            "reference": pay.reference,
            "notes": pay.notes,
            "is_deleted": pay.is_deleted,
            "deleted_at": pay.deleted_at.isoformat() if pay.deleted_at else None,
            "created_at": pay.created_at.isoformat() if pay.created_at else None,
            "updated_at": pay.updated_at.isoformat() if pay.updated_at else None,
        }
        for pay in Payment.objects.select_related("party").order_by("id")
    ]

    return {
        "metadata": {
            "exported_at": timezone.now().isoformat(),
            "version": "1.0",
        },
        "shop_profile": shop_data,
        "categories": categories_data,
        "units": units_data,
        "parties": parties_data,
        "bills": bills_data,
        "payments": payments_data,
    }


def create_database_backup(
    output_dir: str | Path | None = None,
    retention_days: int = 30,
    user=None,
) -> Path:
    """Write a timestamped JSON backup file and prune backups older than retention_days."""
    target_dir = Path(output_dir) if output_dir else (Path(settings.BASE_DIR) / "backups")
    target_dir.mkdir(parents=True, exist_ok=True)

    now = timezone.now()
    filename = f"backup_{now.strftime('%Y%m%d_%H%M%S')}.json"
    filepath = target_dir / filename

    payload = generate_backup_payload()
    filepath.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # Prune old backup_*.json files exceeding retention_days
    if retention_days is not None and retention_days >= 0:
        cutoff_ts = time.time() - (retention_days * 86400)
        for existing in target_dir.glob("backup_*.json"):
            if existing.resolve() == filepath.resolve():
                continue
            try:
                if existing.stat().st_mtime < cutoff_ts:
                    existing.unlink()
            except OSError:
                pass

    log_activity(
        user=user,
        action="backup_created",
        target_type="System",
        description=f"Created database backup {filepath.name}",
        metadata={"filename": filepath.name, "retention_days": retention_days},
    )

    return filepath


def list_backup_files(output_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """Return metadata for existing backup_*.json files sorted newest first."""
    target_dir = Path(output_dir) if output_dir else (Path(settings.BASE_DIR) / "backups")
    if not target_dir.exists():
        return []

    files_info = []
    for path in target_dir.glob("backup_*.json"):
        try:
            stat = path.stat()
            files_info.append(
                {
                    "filename": path.name,
                    "size_bytes": stat.st_size,
                    "size_kb": round(stat.st_size / 1024, 2),
                    "modified_at": datetime.datetime.fromtimestamp(
                        stat.st_mtime, tz=datetime.timezone.utc
                    ),
                }
            )
        except OSError:
            continue

    files_info.sort(key=lambda item: item["modified_at"], reverse=True)
    return files_info


def generate_all_bills_csv() -> str:
    """Generate a comprehensive CSV string of all active bills."""
    bills = (
        Bill.objects.filter(is_deleted=False)
        .select_related("party", "category")
        .order_by("-bill_date", "-id")
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Invoice No",
            "Type",
            "Date",
            "Party",
            "Category",
            "Subtotal",
            "Discount",
            "Tax",
            "Grand Total",
            "Amount Paid",
            "Payment Status",
        ]
    )
    for bill in bills:
        writer.writerow(
            [
                bill.invoice_no or f"BILL-{bill.pk}",
                bill.get_bill_type_display(),
                bill.bill_date.strftime("%Y-%m-%d")
                if hasattr(bill.bill_date, "strftime")
                else str(bill.bill_date),
                bill.party.name if bill.party else "",
                bill.category.name if bill.category else "",
                str(bill.subtotal),
                str(bill.discount),
                str(bill.tax),
                str(bill.grand_total),
                str(bill.amount_paid),
                bill.get_payment_status_display(),
            ]
        )
    return output.getvalue()
