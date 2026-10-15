"""scanning/services/validation.py
================================
Rule engine detecting math discrepancies, missing fields, duplicate invoices, and low confidence.
"""

import contextlib
from datetime import datetime
from datetime import timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from billing.utils import money_round
from bills.models import Bill


def detect_bill_errors(
    extracted_data: Dict[str, Any],
    exclude_bill_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Scan extracted document data against accounting integrity rules.

    Returns a list of error dictionaries containing:
        - error_type
        - field_name
        - severity ('warning' or 'error')
        - message
        - suggested_fix (dict or None)
    """
    errors: List[Dict[str, Any]] = []

    # 1. Math Checks on Line Items
    items = extracted_data.get("items") or []
    item_totals_sum = Decimal("0.00")
    for item in items:
        with contextlib.suppress(ValueError, TypeError, InvalidOperation):
            item_totals_sum += Decimal(str(item.get("line_total") or 0))

    target_subtotal = Decimal("0.00")
    with contextlib.suppress(ValueError, TypeError, InvalidOperation):
        target_subtotal = Decimal(
            str(extracted_data.get("subtotal") or extracted_data.get("grand_total") or 0)
        )
    has_shortfall = target_subtotal > Decimal("0.00") and (
        target_subtotal - item_totals_sum > Decimal("0.05")
    )

    for item in items:
        with contextlib.suppress(ValueError, TypeError, InvalidOperation):
            qty = Decimal(str(item.get("quantity") or 0))
            price_raw = item.get("unit_price")
            line_total_raw = item.get("line_total")
            price = Decimal(str(price_raw or 0))
            line_total = Decimal(str(line_total_raw or 0))

            item_name = item.get("name") or item.get("item_name") or "Item"
            item_name_lower = str(item_name).lower()
            is_explicit_missing = (
                (price_raw is None and line_total_raw is None)
                or "missing" in item_name_lower
                or "without price" in item_name_lower
            )

            if (
                (is_explicit_missing or has_shortfall)
                and price <= Decimal("0.00")
                and line_total <= Decimal("0.00")
            ):
                errors.append(
                    {
                        "error_type": "missing_field",
                        "field_name": "unit_price",
                        "severity": "error",
                        "message": f"Item '{item_name}' is missing price/amount.",
                        "suggested_fix": None,
                    }
                )
            elif qty > Decimal("0.00") and price > Decimal("0.00"):
                expected_line_total = money_round(qty * price)
                diff = abs(expected_line_total - line_total)
                if diff > Decimal("0.01"):
                    # Account for 2-decimal unit price round-half-up effects
                    # (e.g. 130 / 6 = 21.666... -> 21.67; 6 * 21.67 = 130.02, diff 0.02)
                    is_rounding_effect = money_round(line_total / qty) == money_round(
                        price
                    ) and diff <= Decimal("0.05")
                    if not is_rounding_effect:
                        errors.append(
                            {
                                "error_type": "math_mismatch",
                                "field_name": "line_total",
                                "severity": "error",
                                "message": (
                                    f"Item '{item_name}' quantity * unit price "
                                    f"({qty} * {price} = {expected_line_total}) does not match line total ({line_total})."
                                ),
                                "suggested_fix": {"line_total": str(expected_line_total)},
                            }
                        )

    # 2. Subtotal Check
    subtotal_raw = extracted_data.get("subtotal")
    if subtotal_raw is not None and items:
        with contextlib.suppress(ValueError, TypeError, InvalidOperation):
            subtotal = Decimal(str(subtotal_raw))
            if abs(money_round(item_totals_sum) - money_round(subtotal)) > Decimal("0.01"):
                errors.append(
                    {
                        "error_type": "subtotal_mismatch",
                        "field_name": "subtotal",
                        "severity": "error",
                        "message": (
                            f"Sum of item line totals ({money_round(item_totals_sum)}) "
                            f"does not match invoice subtotal ({money_round(subtotal)})."
                        ),
                        "suggested_fix": {"subtotal": str(money_round(item_totals_sum))},
                    }
                )

    # 3. Grand Total Formula Check
    grand_total_raw = extracted_data.get("grand_total")
    if grand_total_raw is not None:
        with contextlib.suppress(ValueError, TypeError, InvalidOperation):
            subtotal_val = Decimal(str(subtotal_raw or item_totals_sum or 0))
            discount_val = Decimal(str(extracted_data.get("discount") or 0))
            tax_val = Decimal(str(extracted_data.get("tax") or 0))
            grand_total_val = Decimal(str(grand_total_raw))

            if subtotal_val > Decimal("0.00"):
                expected_grand_total = money_round(subtotal_val - discount_val + tax_val)
                if abs(expected_grand_total - money_round(grand_total_val)) > Decimal("0.01"):
                    errors.append(
                        {
                            "error_type": "grand_total_mismatch",
                            "field_name": "grand_total",
                            "severity": "error",
                            "message": (
                                f"Grand total ({grand_total_val}) does not match "
                                f"subtotal - discount + tax ({subtotal_val} - {discount_val} + {tax_val} = {expected_grand_total})."
                            ),
                            "suggested_fix": {"grand_total": str(expected_grand_total)},
                        }
                    )

    # 4. Missing Critical Fields Check
    critical_fields = [
        ("invoice_no", "Invoice Number"),
        ("date", "Bill Date"),
        ("grand_total", "Grand Total"),
    ]
    for field_key, field_label in critical_fields:
        val = extracted_data.get(field_key)
        if val is None or (isinstance(val, str) and not val.strip()):
            errors.append(
                {
                    "error_type": "missing_field",
                    "field_name": field_key,
                    "severity": "error",
                    "message": f"Critical field '{field_label}' could not be identified on the document.",
                    "suggested_fix": None,
                }
            )

    # 5. Date Anomalies Check
    date_val = extracted_data.get("date")
    if date_val and isinstance(date_val, str):
        with contextlib.suppress(ValueError, TypeError):
            parsed_date = (
                datetime.strptime(date_val[:10], "%Y-%m-%d").replace(tzinfo=dt_timezone.utc).date()
            )
            today = timezone.now().date()
            if parsed_date > today:
                errors.append(
                    {
                        "error_type": "date_anomaly",
                        "field_name": "date",
                        "severity": "warning",
                        "message": f"Bill date ({parsed_date}) is in the future.",
                        "suggested_fix": {"date": str(today)},
                    }
                )
            elif parsed_date < today - timezone.timedelta(days=365):
                errors.append(
                    {
                        "error_type": "date_anomaly",
                        "field_name": "date",
                        "severity": "warning",
                        "message": f"Bill date ({parsed_date}) is more than one year old.",
                        "suggested_fix": None,
                    }
                )

    # 6. Duplicate Bill Detection
    invoice_no = extracted_data.get("invoice_no")
    if invoice_no and grand_total_raw is not None and date_val:
        with contextlib.suppress(ValueError, TypeError, InvalidOperation, ObjectDoesNotExist):
            query = Bill.objects.filter(
                invoice_no__iexact=str(invoice_no).strip(),
                grand_total=money_round(Decimal(str(grand_total_raw))),
                is_deleted=False,
            )
            target_exclude_id = (
                exclude_bill_id or extracted_data.get("bill_id") or extracted_data.get("id")
            )
            if target_exclude_id:
                query = query.exclude(pk=target_exclude_id)
            existing = query.first()
            if existing:
                errors.append(
                    {
                        "error_type": "duplicate_suspect",
                        "field_name": "invoice_no",
                        "severity": "warning",
                        "message": (
                            f"Possible duplicate: Bill with invoice #{invoice_no} and total "
                            f"{grand_total_raw} already exists in the system (Bill #{existing.pk})."
                        ),
                        "suggested_fix": None,
                    }
                )

    # 7. Low Confidence Warnings
    field_confidence = extracted_data.get("field_confidence") or {}
    for f_name, score in field_confidence.items():
        with contextlib.suppress(ValueError, TypeError):
            if float(score) < 70.0:
                errors.append(
                    {
                        "error_type": "low_confidence",
                        "field_name": f_name,
                        "severity": "warning",
                        "message": f"Field '{f_name}' was extracted with low confidence ({score}%). Please verify.",
                        "suggested_fix": None,
                    }
                )

    return errors
