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
from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone

from billing.utils import money_round
from bills.models import Bill, BillItem
from parties.models import Party
from scanning.exceptions import AIExtractionError, ScanQuotaExceededError
from scanning.models import BillError, BillFile, ScanJob
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

    # Filter out or sanitize invalid negative line items (e.g. hallucinated "off" / negative discounts)
    clean_items = []
    for it in data.get("items", []):
        try:
            raw_price = float(it.get("unit_price") or 0)
            raw_total = float(it.get("line_total") or 0)
        except (ValueError, TypeError):
            raw_price = 0.0
            raw_total = 0.0
        name = str(it.get("name") or "").strip().lower()
        if (raw_price < 0 or raw_total < 0) and name in ("off", "discount", "-"):
            if float(data.get("discount") or 0) == 0.0:
                data["discount"] = abs(raw_total if raw_total != 0 else raw_price)
            continue
        clean_items.append(it)

    # Sanitize and correct single-column line totals and common Urdu item names
    for it in clean_items:
        try:
            raw_price = float(it.get("unit_price") or 0)
            raw_total = float(it.get("line_total") or 0)
            raw_qty = float(it.get("quantity") or 1)
        except (ValueError, TypeError):
            continue

        # Single-column kachi parchi fix:
        # If quantity > 1 and unit_price equals line_total (or does not multiply to line_total),
        # the number written on the slip was the line total, not unit price!
        if (
            raw_qty > 1.0
            and raw_total > 0
            and (
                abs(raw_price - raw_total) <= 0.01 or abs((raw_qty * raw_price) - raw_total) > 0.05
            )
        ):
            it["unit_price"] = round(raw_total / raw_qty, 2)
            if abs(raw_total - round(raw_total)) <= 0.05:
                it["line_total"] = float(round(raw_total))
        elif raw_qty > 1.0 and raw_price > 0:
            raw_lt = raw_qty * raw_price
            int_cand = round(raw_lt)
            if abs(raw_lt - int_cand) <= 0.05 and round(int_cand / raw_qty, 2) == round(
                raw_price, 2
            ):
                it["line_total"] = float(int_cand)

        # Urdu item naming correction for common kitchen items
        urdu_name = str(it.get("urdu_name") or "").strip()
        name_lower = str(it.get("name") or "").strip().lower()
        if "اچار" in urdu_name or "achar" in name_lower:
            it["name"] = "Achar (Pickles)"
            it["urdu_name"] = "اچار"

    # -------------------------------------------------------------------------
    # Rule 15: Retail / POS Receipts with Savings / Discount & FBR Service Fee
    # (e.g. Euro Store, Supermarket POS receipts with "Saving" / "MKT Price" vs "Sale Price")
    # -------------------------------------------------------------------------
    total_disc = float(data.get("discount") or 0.0)
    tax_val = float(data.get("tax") or 0.0)
    gt_val = float(data.get("grand_total") or 0.0)

    # 1. FBR Service Fee detection (e.g. 1.00 PKR on Pakistani POS receipts)
    if tax_val == 0.0 and gt_val > 0:
        current_sub = float(data.get("subtotal") or 0.0)
        items_st = sum(float(it.get("line_total") or 0.0) for it in clean_items)
        if (
            abs((current_sub - total_disc + 1.0) - gt_val) <= 0.05
            or abs((items_st - total_disc + 1.0) - gt_val) <= 0.05
            or abs((items_st + 1.0) - gt_val) <= 0.05
        ):
            data["tax"] = 1.0
            tax_val = 1.0

    # 2. Saving amount reconciliation:
    # If saving amount was not added to item prices (items extracted at net sale prices),
    # add saving amount to item price/amount and minus at the end from grand total as discount.
    items_sum = sum(float(it.get("line_total") or 0.0) for it in clean_items)
    if total_disc > 0.0 and gt_val > 0.0:
        needs_saving_added = False
        if (
            abs((items_sum + tax_val) - gt_val) <= 0.05
            and abs((items_sum - total_disc + tax_val) - gt_val) > 0.05
            or any(float(it.get("discount") or 0.0) > 0 for it in clean_items)
            and abs((items_sum - total_disc + tax_val) - gt_val) > 0.05
        ):
            needs_saving_added = True

        if needs_saving_added:
            items_with_disc = [it for it in clean_items if float(it.get("discount") or 0.0) > 0]
            if items_with_disc:
                for it in items_with_disc:
                    d_amt = float(it.get("discount") or 0.0)
                    qty = float(it.get("quantity") or 1.0) or 1.0
                    it["line_total"] = round(float(it.get("line_total") or 0.0) + d_amt, 2)
                    it["unit_price"] = round(it["line_total"] / qty, 2)
            elif len(clean_items) == 1:
                it = clean_items[0]
                qty = float(it.get("quantity") or 1.0) or 1.0
                it["line_total"] = round(float(it.get("line_total") or 0.0) + total_disc, 2)
                it["unit_price"] = round(it["line_total"] / qty, 2)
                it["discount"] = total_disc

            new_subtotal = round(sum(float(it.get("line_total") or 0.0) for it in clean_items), 2)
            data["subtotal"] = new_subtotal

    # -------------------------------------------------------------------------
    # Rule 16: Fee Challans & Pre-Printed Forms with Blank Rows Mistaken for Grand Total
    # (e.g. "Arreras" / "Arrears" / "Others" row right above Grand Total receiving
    # the Grand Total amount when the slip cell was actually blank)
    # -------------------------------------------------------------------------
    if gt_val > 0.0 and len(clean_items) > 1:
        current_items_sum = sum(float(it.get("line_total") or 0.0) for it in clean_items)
        diff = round(current_items_sum - total_disc + tax_val - gt_val, 2)
        if diff > 0.05:
            for it in reversed(clean_items):
                it_name = str(it.get("name") or "").strip().lower()
                it_lt = float(it.get("line_total") or 0.0)
                rem_sum = round(current_items_sum - it_lt - total_disc + tax_val, 2)
                if abs(rem_sum - gt_val) <= 0.05 and (
                    abs(it_lt - gt_val) <= 0.05 or abs(it_lt - diff) <= 0.05
                ):
                    is_candidate = (
                        "arrer" in it_name
                        or "arrear" in it_name
                        or "other" in it_name
                        or "late" in it_name
                        or it == clean_items[-1]
                    )
                    if is_candidate:
                        it["unit_price"] = 0.0
                        it["line_total"] = 0.0
                        it["discount"] = 0.0
                        it["tax"] = 0.0
                        new_subtotal = round(
                            sum(float(x.get("line_total") or 0.0) for x in clean_items), 2
                        )
                        data["subtotal"] = new_subtotal
                        break

    data["items"] = clean_items

    return data


EXTRACTION_SYSTEM_PROMPT = """You are an expert AI bill, receipt, and invoice scanner specialized in extracting financial documents in English and Urdu.
Extract all details from the provided document image(s) or PDF according to the schema below.
Follow these critical rules:
1. Return ONLY a single valid JSON object matching the schema. No markdown code blocks, no explanation text outside JSON.
2. HANDWRITTEN CORRECTIONS, CUTTING, AND STRIKETHROUGHS (CRITICAL / کٹنگ اور کاٹے ہوئے نمبر):
   In handwritten bills and receipts (کچی پرچی / ہاتھ سے لکھا بل), shopkeepers frequently correct prices or quantities by crossing them out, encircling them, scribbling over them, or cutting them (کٹنگ / kaatna / خط کھینچنا / گول دائرہ لگانا).
   - RULE ON CIRCLED / STRUCK NUMBERS:
     * ANY number with a circle/oval around it, slash through it, strikethrough, or cross-out is the VOID, REJECTED, OLD value ("cutting wali value" / کٹنگ والی رقم).
     * NEVER, UNDER ANY CIRCUMSTANCES, extract or use the circled or struck-through number!
     * ALWAYS extract the CLEAN, UN-CIRCLED, UN-STRUCK replacement number written next to it, above it, or below it.
     * EXAMPLE FROM REAL DOCUMENT:
       If next to "1- چکن 1 کلو" you see "450" and a circled "350":
       -> "350" is the circled / cutting value (MUST BE IGNORED AND REJECTED).
       -> "450" is the active, valid replacement price (MUST BE EXTRACTED).
       -> Therefore unit_price = 450, line_total = 450.
   - MATHEMATICAL RECONCILIATION AGAINST SLIP GRAND TOTAL:
     * In handwritten slips, the shopkeeper writes the grand total at the bottom (e.g. "ٹوٹل 2670").
     * Always cross-check your line items sum against the slip's handwritten grand total!
     * If one candidate price (e.g. 450) produces a total matching or closest to the handwritten slip total (2670), while the other (e.g. 350) is off by 100, that mathematically proves 450 is the correct active number and 350 was the canceled cutting!
   - Base all calculations (line total, subtotal, grand total) on the corrected final numbers, NEVER the struck-through / cutting numbers.
3. Read handwritten and printed bills in English, Urdu, and mixed text. For vendor and item names: provide the standard English / Roman transliterated name in 'name' (e.g. 'Arif Chicken Center') AND provide the Urdu text in 'urdu_name' (e.g. 'عارف چکن سنٹر') if written in Urdu script. If only English is present, put it in 'name'.
4. Always extract any phone or mobile number (e.g. '0300-1234567', 'Mob:', 'Ph:', 'Tel:') for the vendor and customer into vendor.phone or customer.phone whenever visible on the document.
5. If a field is not present or cannot be read with confidence, set it to null. NEVER invent or guess data.
6. Accurately extract all line items in order: item name, quantity, unit, unit price, discount, tax, line total, confidence (0-100).
7. Accurately extract totals: subtotal, discount, tax, other charges, grand total, amount paid, balance due.
8. For multi-page bills, merge all pages into a single consolidated document.
9. Set currency (e.g. "PKR", "USD") and payment method ("cash", "card", "online", "credit") if identifiable.
10. If there are uncertainties, illegible text, or calculation discrepancies, list them in the "warnings" array.
11. DECIMAL ROUNDING RULE (ROUND HALF-UP):
    Whenever calculating or extracting prices, unit rates, or totals with decimals:
    - Always round to 2 decimal places using standard half-up rounding: look at the 3rd decimal digit after the dot; if the 3rd digit is 5 or greater, round UP by adding 1 to the second decimal digit (e.g. .666 becomes .67).
    - NEVER truncate digits!
    - Example: 130 total for 6 eggs -> 130 / 6 = 21.666... -> MUST be rounded to 21.67 (NOT 21.66).
    - Example: 100 / 3 = 33.333... -> 33.33.
    - Example: 35 / 3 = 11.666... -> 11.67.
12. RULES ON DISCOUNTS VS ADDITIONAL PAYMENTS / INSTALLMENTS:
    - In South Asian / Pakistani slips and cash memos (کچی پرچی / کیش میمو), handwritten notes below the main items (such as "Cash dp", "adv", "c/o", "مزید", "وصول", "جمع", or scribbles with amounts like 500) represent cash deposits, installment payments, or extra items/charges.
    - NEVER interpret cursive scribbles or subsequent payments as discounts or "off" (do NOT extract "off -200" or similar negative items).
    - NEVER produce line items with negative unit_price or negative line_total! All items MUST have positive or zero prices.
    - ONLY extract a discount if the document explicitly and clearly writes "Discount", "رعایت", or "چھوٹ". Otherwise, discount must be 0.
13. SINGLE-COLUMN NUMBER SLIPS (KACHI PARCHI / کچی پرچی):
    - When a handwritten slip only has ONE column of numbers written for items (e.g., "5 - انڈے 6 عدد ... 130", "11 - دودھ 2 کلو ... 440", "7 - مارکر 2 عدد ... 40"):
    - That highlighted number on the left/right is ALWAYS the LINE TOTAL (line_total), NOT the unit price! The shopkeeper only wrote the total amount for that line.
    - You MUST set:
      * line_total = the written amount (e.g. 130 for 6 eggs; 440 for 2 kg milk; 40 for 2 markers).
      * unit_price = line_total / quantity, rounded half-up to 2 decimals (e.g. 130 / 6 = 21.67; 440 / 2 = 220.0; 40 / 2 = 20.0).
      * NEVER put the line total into unit_price when quantity > 1!
14. COMMON URDU VOCABULARY & FOOD ITEMS:
    - "اچار" = Achar (Pickles / Pickling). NEVER confuse or translate "اچار" as "Tea" / "چائے"!
    - "چائے" = Tea
    - "زردہ رنگ" = Food Color (Zarda Rang)
    - "چاول" = Rice
    - "چکن" = Chicken
    - "دال چنا" = Daal Chana
    - "دال ماش" = Daal Mash
    - "گھی" = Ghee
    - "دودھ" = Milk
    - Always verify every handwritten line number against the handwritten grand total (ٹوٹل 2670) at the bottom.
15. RETAIL / POS RECEIPTS WITH SAVING & FBR SERVICE FEE (e.g. Euro Store, Supermarkets):
    - SAVING / MKT PRICE:
      When a receipt shows a "Saving" column, "Amount Saving", or "MKT Price" vs "Sale Price" (e.g. Bunny's Milky Bread: Sale Price 190, Saving 40, MKT Price 230):
      * Always add the saving amount into the item's unit_price and line_total so that each line item reflects its full pre-discount amount (e.g. unit_price = 230.0, line_total = 230.0).
      * The sum of all item line totals will then equal the pre-discount total ("ACTUAL PRICE", e.g. 372.0).
      * Record this pre-discount total in "subtotal" (e.g. 372.0).
      * Put the total savings into "discount" (e.g. 40.0) so it is deducted at the end from grand total.
    - FBR SERVICE FEE / POS FEE:
      * On Pakistani POS receipts, always check for "FBR Service Fee", "POS Fee", or "FBR Fee" (typically 1.00 PKR).
      * ALWAYS extract this fee into "tax" (e.g. tax = 1.0).
    - FORMULA VERIFICATION:
      * Subtotal (372.0) - Discount (40.0) + Tax / FBR Fee (1.0) = Grand Total (333.0).
      * This ensures the line items, subtotal, discount, FBR fee, and grand total all reconcile perfectly.
16. PRE-PRINTED FORMS, FEE CHALLANS & BLANK CELLS VS GRAND TOTAL (خالی خانے اور گرینڈ ٹوٹل):
    - On school fee challans, admission forms, or slips with printed fee categories (e.g. 'Registration fee', 'Admission fee', 'Tuition fee', 'Generator fee', 'Annual funds', 'Others', 'Arrears' / 'Arreras', 'Grand Total'):
    - Look carefully at each row. If a cell or row is BLANK / EMPTY (no amount written in that specific row's box), set unit_price = 0 and line_total = 0.
    - NEVER confuse or assign the 'Grand Total' amount to the row right above it (such as 'Arrears' or 'Others')!
    - For example, if 'Annual funds' is 5000 and the bottom 'Grand Total' box is 5000, and 'Arrears' is blank:
      * Annual funds = 5000.
      * Arrears = 0 (do NOT extract 5000 for Arrears!).
      * Grand Total = 5000.
      * The sum of fee items MUST reconcile with Grand Total (5000 = 5000).

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
            system_instruction=EXTRACTION_SYSTEM_PROMPT,
            temperature=0.0,
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
    close_old_connections()
    check_scan_quota_available()

    job.status = ScanJob.Status.PROCESSING
    job.save(update_fields=["status"])

    start_time = time.time()

    try:
        files = list(job.files.all())
        first_file = files[0] if files else None

        # FAST-TRACK DUPLICATE DOCUMENT CACHE:
        # If an identical document (same file_hash) was already scanned and has a bill,
        # reuse its extracted data instantly in 0.05s instead of waiting 10-15s for Gemini AI!
        cached_existing_job = None
        if first_file and first_file.file_hash:
            bf_query = BillFile.objects.filter(
                file_hash=first_file.file_hash, bill__isnull=False
            ).exclude(scan_job=job)
            if job.created_by is not None:
                if getattr(job.created_by, "is_superuser", False):
                    bf_query = bf_query.filter(
                        Q(bill__created_by=job.created_by) | Q(bill__created_by__isnull=True)
                    )
                else:
                    bf_query = bf_query.filter(bill__created_by=job.created_by)
            existing_bf = bf_query.select_related("scan_job__bill", "bill").order_by("-id").first()
            if existing_bf and existing_bf.scan_job and existing_bf.scan_job.extracted_data:
                cached_existing_job = existing_bf.scan_job

        if cached_existing_job:
            validated_data = validate_extraction_schema(dict(cached_existing_job.extracted_data))
            job.raw_response = cached_existing_job.raw_response
            is_fast_duplicate = True
            prev_bill = cached_existing_job.bill
            token_count_val = 0
        else:
            extractor = get_ai_extractor(job.provider)
            raw_result = extractor.extract(*files)
            validated_data = validate_extraction_schema(raw_result)
            is_fast_duplicate = False
            prev_bill = None
            token_count_val = getattr(extractor, "last_token_count", 1250) or 1250

        # 1. Resolve Party (Vendor and Customer)
        vendor_data = validated_data.get("vendor") or {}
        party, _ = resolve_scan_party(
            vendor_data, party_type=Party.PartyType.VENDOR, user=job.created_by
        )

        # Auto-create or match Customer profile if customer details were extracted
        customer_data = validated_data.get("customer") or {}
        customer_party = None
        cust_name = str(customer_data.get("name") or "").strip()
        if cust_name and cust_name.lower() not in (
            "null",
            "none",
            "n/a",
            "unknown",
            "walk-in customer",
        ):
            customer_party, _ = resolve_scan_party(
                customer_data, party_type=Party.PartyType.CUSTOMER, user=job.created_by
            )

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

        notes_content = ""
        if customer_party:
            notes_content = f"Client / Customer: {customer_party.name}"
            if customer_party.phone:
                notes_content += f" ({customer_party.phone})"

        bill = Bill.objects.create(
            party=party,
            customer=customer_party,
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
            notes=notes_content,
            created_by=job.created_by,
        )

        # 4. Create Line Items
        for idx, it in enumerate(validated_data.get("items", []), start=1):
            qty = Decimal(str(it.get("quantity") or 1))
            lt = money_round(Decimal(str(it.get("line_total") or 0)))
            raw_price = Decimal(str(it.get("unit_price") or 0))

            if qty > Decimal("0.00") and lt > Decimal("0.00"):
                computed_price = money_round(lt / qty)
                if (
                    raw_price == Decimal("0.00")
                    or (qty > Decimal("1.00") and abs(raw_price - lt) <= Decimal("0.01"))
                    or abs(money_round(qty * raw_price) - lt) > Decimal("0.05")
                ):
                    price = computed_price
                else:
                    price = money_round(raw_price)
                    # If raw_price was truncated (e.g. 21.66 instead of 21.67):
                    # when lt / qty rounds half-up to computed_price, use the rounded price
                    if abs(price - computed_price) <= Decimal("0.01"):
                        price = computed_price
            else:
                price = money_round(raw_price)

            raw_lt = qty * price
            integer_cand = Decimal(str(round(float(raw_lt))))
            max_diff = max(Decimal("0.05"), money_round(qty * Decimal("0.0055")))
            if (
                qty > Decimal("1.00")
                and abs(raw_lt - integer_cand) <= max_diff
                and money_round(integer_cand / qty) == price
            ):
                lt = integer_cand
            elif lt == Decimal("0.00"):
                lt = money_round(raw_lt)

            # Keep validated_data in sync for detect_bill_errors
            it["unit_price"] = float(price)
            it["line_total"] = float(lt)

            item_name = str(it.get("name") or it.get("item_name") or f"Item {idx}").strip()
            urdu_item_name = str(it.get("urdu_name") or it.get("urdu_item_name") or "").strip()
            unit_val = str(it.get("unit") or "pcs").strip()

            BillItem.objects.create(
                bill=bill,
                serial_no=it.get("serial_no") or idx,
                item_name=item_name or f"Item {idx}",
                urdu_item_name=urdu_item_name,
                quantity=qty,
                unit=unit_val,
                unit_price=price,
                line_total=lt,
            )

        # 5. Detect and attach errors
        discrepancies = detect_bill_errors(
            validated_data, exclude_bill_id=bill.pk, user=job.created_by
        )
        if is_fast_duplicate and prev_bill and not prev_bill.is_deleted:
            discrepancies.append(
                {
                    "error_type": BillError.ErrorType.DUPLICATE_SUSPECT,
                    "field_name": "document_file",
                    "severity": "warning",
                    "message": f"Duplicate Bill: This exact document was previously scanned as Bill #{prev_bill.pk} on {prev_bill.bill_date}.",
                }
            )
        for disc in discrepancies:
            BillError.objects.create(
                bill=bill,
                error_type=disc["error_type"],
                field_name=disc.get("field_name") or "",
                severity=disc.get("severity") or "warning",
                message=disc.get("message") or "",
                suggested_fix=disc.get("suggested_fix"),
            )

        # 6. Associate files with resulting Bill
        job.files.update(bill=bill)

        # 7. Complete ScanJob
        job.bill = bill
        job.status = ScanJob.Status.COMPLETED
        job.extracted_data = validated_data
        job.token_count = token_count_val
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
    finally:
        close_old_connections()
