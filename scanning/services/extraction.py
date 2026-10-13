"""scanning/services/extraction.py
================================
AI Vision Extraction pipeline, schema validator, mock extractor, and quota enforcement.
"""

import json
import time
from decimal import Decimal
from pathlib import Path
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


EXTRACTION_SYSTEM_PROMPT = """You are an expert AI bill, receipt, and invoice scanner specialized in extracting financial documents in English and Urdu.
Extract all details from the provided document image(s) or PDF according to the schema below.
Follow these critical rules:
1. Return ONLY a single valid JSON object matching the schema. No markdown code blocks, no explanation text outside JSON.
2. Read handwritten and printed bills in English, Urdu, and mixed text. For vendor and item names: provide the standard English / Roman transliterated name in 'name' (e.g. 'Arif Chicken Center') AND provide the Urdu text in 'urdu_name' (e.g. 'عارف چکن سنٹر') if written in Urdu script. If only English is present, put it in 'name'.
3. If a field is not present or cannot be read with confidence, set it to null. NEVER invent or guess data.
4. Accurately extract all line items in order: item name, quantity, unit, unit price, discount, tax, line total, confidence (0-100).
5. Accurately extract totals: subtotal, discount, tax, other charges, grand total, amount paid, balance due.
6. For multi-page bills, merge all pages into a single consolidated document.
7. Set currency (e.g. "PKR", "USD") and payment method ("cash", "card", "online", "credit") if identifiable.
8. If there are uncertainties, illegible text, or calculation discrepancies, list them in the "warnings" array.

Schema to return:
{
  "document_type": "printed",
  "languages": ["en", "ur"],
  "vendor": {"name": null, "urdu_name": null, "phone": null, "address": null, "tax_no": null},
  "customer": {"name": null, "phone": null, "address": null},
  "invoice_no": null,
  "date": "YYYY-MM-DD",
  "time": "HH:MM",
  "currency": "PKR",
  "items": [
    {
      "serial_no": 1,
      "name": "",
      "urdu_name": null,
      "quantity": 1,
      "unit": "pcs",
      "unit_price": 0,
      "discount": 0,
      "tax": 0,
      "line_total": 0,
      "confidence": 95
    }
  ],
  "subtotal": null,
  "discount": 0,
  "tax": 0,
  "other_charges": 0,
  "grand_total": null,
  "paid_amount": 0,
  "balance_due": null,
  "payment_method": null,
  "suggested_category": "",
  "field_confidence": {"vendor_name": 90, "date": 90, "grand_total": 90},
  "warnings": []
}
"""


def get_file_bytes_and_mime(file_obj: Any) -> tuple[bytes, str]:
    """Extract raw bytes and detected MIME type from BillFile, UploadedFile, or path."""
    name = ""
    data = b""

    if hasattr(file_obj, "file") and hasattr(file_obj.file, "name"):
        field = file_obj.file
        name = getattr(field, "name", "")
        try:
            field.open("rb")
            data = field.read()
        except Exception:
            if hasattr(field, "path"):
                with open(field.path, "rb") as fp:
                    data = fp.read()
    elif hasattr(file_obj, "read"):
        name = getattr(file_obj, "name", "")
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        data = file_obj.read()
    elif isinstance(file_obj, (str, Path)):
        name = str(file_obj)
        with open(file_obj, "rb") as fp:
            data = fp.read()
    elif isinstance(file_obj, bytes):
        data = file_obj
        name = "image.jpg"
    else:
        raise ValidationError(f"Unsupported file input type: {type(file_obj)}")

    ext = Path(name).suffix.lower()
    if ext in [".jpg", ".jpeg"]:
        mime = "image/jpeg"
    elif ext == ".png":
        mime = "image/png"
    elif ext == ".webp":
        mime = "image/webp"
    elif ext == ".pdf":
        mime = "application/pdf"
    else:
        mime = "image/jpeg"

    return data, mime


def _clean_and_parse_json(raw_text: str) -> Dict[str, Any]:
    """Clean markdown code fences and parse JSON payload."""
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    elif "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        text = text[start:end]
    return json.loads(text)


class GeminiAIExtractor:
    """Vision-capable AI extractor powered by Google Gemini API."""

    def __init__(self, api_key: str, model_name: str | None = None):
        self.api_key = api_key
        self.model_name = model_name or getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.last_token_count = 1250

    def extract(self, *files: Any) -> Dict[str, Any]:
        """Extract bill structured data using Gemini vision."""
        if not files:
            raise ValidationError("No files provided for AI extraction.")

        try:
            from google import genai
            from google.genai import types
        except ImportError as err:
            raise AIExtractionError(
                "The 'google-genai' library is required for Gemini AI extraction. "
                "Please run: pip install google-genai"
            ) from err

        try:
            client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(timeout=30000),
            )
        except (TypeError, AttributeError):
            client = genai.Client(api_key=self.api_key)
        contents = []

        for f in files:
            data, mime = get_file_bytes_and_mime(f)
            contents.append(types.Part.from_bytes(data=data, mime_type=mime))

        contents.append(EXTRACTION_SYSTEM_PROMPT)

        config = types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        )

        candidate_models = [self.model_name]
        for fallback in ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-latest"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        response = None
        last_error = None
        for m_name in candidate_models:
            try:
                response = client.models.generate_content(
                    model=m_name,
                    contents=contents,
                    config=config,
                )
                if response:
                    break
            except Exception as exc:
                last_error = exc

        if response is None:
            raise AIExtractionError(f"Gemini API request failed: {last_error}") from last_error

        raw_text = getattr(response, "text", "") or ""
        usage = getattr(response, "usage_metadata", None)
        if usage:
            self.last_token_count = getattr(usage, "total_token_count", 0) or (
                getattr(usage, "prompt_token_count", 0)
                + getattr(usage, "candidates_token_count", 0)
            )

        try:
            return _clean_and_parse_json(raw_text)
        except Exception as parse_err:
            raise AIExtractionError(
                f"Failed to parse structured JSON from Gemini response: {parse_err}"
            ) from parse_err


class ClaudeAIExtractor:
    """Vision-capable AI extractor powered by Anthropic Claude API."""

    def __init__(self, api_key: str, model_name: str | None = None):
        self.api_key = api_key
        self.model_name = model_name or "claude-3-5-sonnet-20241022"
        self.last_token_count = 1250

    def extract(self, *files: Any) -> Dict[str, Any]:
        """Extract structured bill JSON using Claude Messages API."""
        if not files:
            raise ValidationError("No files provided for AI extraction.")

        try:
            import base64

            import httpx
        except ImportError as err:
            raise AIExtractionError(
                "httpx package is required for Claude vision extraction."
            ) from err

        content_parts = []
        for f in files:
            data, mime = get_file_bytes_and_mime(f)
            b64_data = base64.b64encode(data).decode("utf-8")
            if mime == "application/pdf":
                content_parts.append(
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": b64_data,
                        },
                    }
                )
            else:
                content_parts.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime,
                            "data": b64_data,
                        },
                    }
                )

        content_parts.append({"type": "text", "text": EXTRACTION_SYSTEM_PROMPT})

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": content_parts}],
        }

        try:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=60.0,
            )
            resp.raise_for_status()
            res_data = resp.json()
            raw_text = res_data["content"][0]["text"]
            self.last_token_count = res_data.get("usage", {}).get("input_tokens", 0) + res_data.get(
                "usage", {}
            ).get("output_tokens", 0)
            return _clean_and_parse_json(raw_text)
        except Exception as exc:
            raise AIExtractionError(f"Claude API request failed: {exc}") from exc


class MockAIExtractor:
    """Deterministic, offline AI vision extractor for testing and development."""

    def __init__(self):
        self.last_token_count = 1250

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
            "warnings": [
                "Extracted using Mock AI Provider for offline testing. Configure GEMINI_API_KEY in .env for real vision extraction."
            ],
        }


def get_ai_extractor(provider: str | None = None):
    """Factory returning active AI extractor based on settings or explicit provider."""
    active = provider or getattr(settings, "AI_PROVIDER", "gemini")

    if active == "gemini":
        api_key = getattr(settings, "GEMINI_API_KEY", "")
        if not api_key:
            raise AIExtractionError(
                "Google Gemini API key is not configured. Please set GEMINI_API_KEY "
                "in your .env file to enable AI bill extraction, or set AI_PROVIDER=mock for offline testing."
            )
        return GeminiAIExtractor(api_key=api_key)

    if active == "claude":
        api_key = getattr(settings, "CLAUDE_API_KEY", "")
        if not api_key:
            raise AIExtractionError(
                "Anthropic Claude API key is not configured. Please set CLAUDE_API_KEY "
                "in your .env file to enable AI bill extraction, or set AI_PROVIDER=mock for offline testing."
            )
        return ClaudeAIExtractor(api_key=api_key)

    if active == "mock":
        return MockAIExtractor()

    return MockAIExtractor()


def process_scan_job(job: ScanJob) -> Bill:
    """Execute end-to-end scanning pipeline for a ScanJob."""
    check_scan_quota_available()

    job.status = ScanJob.Status.PROCESSING
    job.save(update_fields=["status"])

    start_time = time.time()
    extractor = get_ai_extractor(job.provider)

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
        job.token_count = getattr(extractor, "last_token_count", 1250) or 1250
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
