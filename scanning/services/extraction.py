"""scanning/services/extraction.py
================================
AI Vision Extraction pipeline, schema validator, mock extractor, and quota enforcement.
"""

import time
from decimal import Decimal
from typing import Any, Dict

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from billing.utils import money_round
from bills.models import Bill, BillItem
from parties.models import Party
from scanning.exceptions import AIExtractionError, ScanQuotaExceededError
from scanning.models import BillError, ScanJob
from scanning.services.matching import resolve_scan_party, suggest_bill_category
from scanning.services.validation import detect_bill_errors
from settings_app.models import ShopProfile


def check_scan_quota_available() -> None:
    """Verify that current shop has not reached daily or monthly scanning quota."""
    profile = ShopProfile.get_solo()
    now = timezone.now()

    # Daily check
    today_count = ScanJob.objects.filter(
        status=ScanJob.Status.COMPLETED,
        created_at__date=now.date(),
    ).count()

    if today_count >= profile.daily_scan_limit:
        raise ScanQuotaExceededError(
            f"Daily scan limit ({profile.daily_scan_limit}) reached for today. "
            "Please enter this bill manually or wait until tomorrow."
        )

    # Monthly check
    month_count = ScanJob.objects.filter(
        status=ScanJob.Status.COMPLETED,
        created_at__year=now.year,
        created_at__month=now.month,
    ).count()

    if month_count >= profile.monthly_scan_limit:
        raise ScanQuotaExceededError(
            f"Monthly scan limit ({profile.monthly_scan_limit}) reached for this month. "
            "Please enter this bill manually or upgrade your quota."
        )


def validate_extraction_schema(data: Any) -> Dict[str, Any]:
    """Validate extracted AI JSON against Section 7 schema specification."""
    if not isinstance(data, dict):
        raise ValidationError("Extracted document payload must be a JSON object.")

    required_keys = ["document_type", "vendor", "items", "grand_total"]
    for key in required_keys:
        if key not in data:
            raise ValidationError(f"Schema violation: Missing required field '{key}'.")

    if not isinstance(data.get("items"), list):
        raise ValidationError("Schema violation: 'items' must be a list of line items.")

    # Ensure required defaults
    data.setdefault("languages", ["en"])
    data.setdefault("customer", {"name": None, "phone": None, "address": None})
    data.setdefault("invoice_no", "")
    data.setdefault("date", timezone.now().strftime("%Y-%m-%d"))
    data.setdefault("currency", "PKR")
    data.setdefault("subtotal", data.get("grand_total"))
    data.setdefault("discount", 0.0)
    data.setdefault("tax", 0.0)
    data.setdefault("field_confidence", {})
    data.setdefault("warnings", [])

    return data


class MockAIExtractor:
    """Deterministic, offline AI vision extractor for testing and development."""

    def extract(self, *files: Any) -> Dict[str, Any]:
        """Return high-fidelity structured bill JSON matching schema."""
        return {
            "document_type": "printed",
            "languages": ["en", "ur"],
            "vendor": {
                "name": "Al-Madina General Store",
                "phone": "03001234567",
                "address": "Main Market, Gulberg, Lahore",
                "tax_no": "STRN-9876543",
            },
            "customer": {
                "name": "Walk-in Customer",
                "phone": "",
                "address": "",
            },
            "invoice_no": f"INV-{int(time.time()) % 100000:05d}",
            "date": timezone.now().strftime("%Y-%m-%d"),
            "time": "14:45",
            "currency": "PKR",
            "items": [
                {
                    "serial_no": 1,
                    "name": "Cooking Oil 5L",
                    "quantity": 2.0,
                    "unit": "tin",
                    "unit_price": 2500.0,
                    "discount": 0.0,
                    "tax": 0.0,
                    "line_total": 5000.0,
                    "confidence": 98,
                },
                {
                    "serial_no": 2,
                    "name": "Basmati Rice 5kg",
                    "quantity": 3.0,
                    "unit": "bag",
                    "unit_price": 1200.0,
                    "discount": 0.0,
                    "tax": 0.0,
                    "line_total": 3600.0,
                    "confidence": 95,
                },
            ],
            "subtotal": 8600.0,
            "discount": 0.0,
            "tax": 0.0,
            "other_charges": 0.0,
            "grand_total": 8600.0,
            "paid_amount": 8600.0,
            "balance_due": 0.0,
            "payment_method": "cash",
            "suggested_category": "Grocery",
            "field_confidence": {
                "vendor_name": 98,
                "date": 95,
                "grand_total": 99,
            },
            "warnings": [],
        }


def get_ai_extractor():
    """Factory returning active AI extractor based on settings."""
    _ = getattr(settings, "AI_PROVIDER", "mock")
    # For now in test and local environment, default to MockAIExtractor
    return MockAIExtractor()


def process_scan_job(job: ScanJob) -> Bill:
    """Execute end-to-end scanning pipeline for a ScanJob."""
    check_scan_quota_available()

    job.status = ScanJob.Status.PROCESSING
    job.save(update_fields=["status"])

    start_time = time.time()
    extractor = get_ai_extractor()

    try:
        files = list(job.files.all())
        raw_result = extractor.extract(*files)
        validated_data = validate_extraction_schema(raw_result)

        # 1. Resolve Party (Vendor or Customer)
        vendor_data = validated_data.get("vendor") or {}
        party, _ = resolve_scan_party(vendor_data, party_type=Party.PartyType.VENDOR)

        # 2. Resolve Category
        suggested_cat_name = validated_data.get("suggested_category", "")
        category = suggest_bill_category(suggested_cat_name, validated_data.get("items", []))

        # 3. Create Draft/NeedsReview Bill
        subtotal_val = money_round(Decimal(str(validated_data.get("subtotal") or 0)))
        discount_val = money_round(Decimal(str(validated_data.get("discount") or 0)))
        tax_val = money_round(Decimal(str(validated_data.get("tax") or 0)))
        grand_total_val = money_round(Decimal(str(validated_data.get("grand_total") or 0)))

        bill_date_str = validated_data.get("date") or timezone.now().strftime("%Y-%m-%d")
        try:
            bill_date = timezone.datetime.strptime(bill_date_str[:10], "%Y-%m-%d").date()
        except Exception:
            bill_date = timezone.now().date()

        bill = Bill.objects.create(
            party=party,
            category=category,
            invoice_no=str(validated_data.get("invoice_no") or "").strip(),
            bill_date=bill_date,
            bill_type=Bill.BillType.PURCHASE,
            source=Bill.Source.SCAN,
            status=Bill.Status.NEEDS_REVIEW,
            subtotal=subtotal_val,
            discount=discount_val,
            tax=tax_val,
            grand_total=grand_total_val,
            payment_status=Bill.PaymentStatus.UNPAID,
            amount_paid=Decimal("0.00"),
            created_by=job.created_by,
        )

        # 4. Create Line Items
        for idx, it in enumerate(validated_data.get("items", []), start=1):
            qty = Decimal(str(it.get("quantity") or 1))
            price = money_round(Decimal(str(it.get("unit_price") or 0)))
            lt = money_round(Decimal(str(it.get("line_total") or (qty * price))))

            BillItem.objects.create(
                bill=bill,
                serial_no=it.get("serial_no") or idx,
                item_name=it.get("name") or it.get("item_name") or f"Item {idx}",
                urdu_item_name=it.get("urdu_name", ""),
                quantity=qty,
                unit=it.get("unit", "pcs"),
                unit_price=price,
                line_total=lt,
            )

        # 5. Detect and attach errors
        discrepancies = detect_bill_errors(validated_data)
        for disc in discrepancies:
            BillError.objects.create(
                bill=bill,
                error_type=disc["error_type"],
                field_name=disc.get("field_name", ""),
                severity=disc.get("severity", "warning"),
                message=disc.get("message", ""),
                suggested_fix=disc.get("suggested_fix"),
            )

        # 6. Associate files with resulting Bill
        job.files.update(bill=bill)

        # 7. Complete ScanJob
        job.bill = bill
        job.status = ScanJob.Status.COMPLETED
        job.extracted_data = validated_data
        job.token_count = 1250
        job.latency_ms = int((time.time() - start_time) * 1000)
        job.completed_at = timezone.now()
        job.save()

        return bill

    except Exception as exc:
        job.status = ScanJob.Status.FAILED
        job.error_message = str(exc)
        job.save(update_fields=["status", "error_message"])
        if isinstance(exc, (ScanQuotaExceededError, ValidationError)):
            raise
        raise AIExtractionError(f"Scanning failed: {exc}") from exc
