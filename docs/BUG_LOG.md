# Bug Log

All confirmed bugs are recorded here. Each entry has: what happened, why, how it was fixed, and the regression test that prevents it from coming back.

> Format: `## BUG-<number>: <short title>`

---

## BUG-001: Bill Scanning Showed Previous/Static Mock Bill Instead of Real AI Extraction

- **Date:** 2026-10-13
- **Reported by:** user
- **Severity:** High
- **What happened:** When uploading new bill documents or photos, the system repeatedly extracted identical dummy bill details ("Al-Madina General Store", 2x Cooking Oil, 3x Rice, total 8,600.00), giving the appearance of showing a previously saved bill rather than extracting the newly uploaded document.
- **Root cause:** 
  1. `scanning/views.py` hardcoded `ScanJob.objects.create(provider="mock")` instead of respecting `settings.AI_PROVIDER`.
  2. `scanning/services/extraction.py` factory `get_ai_extractor()` unconditionally returned `MockAIExtractor()`, ignoring `AI_PROVIDER` and API keys.
  3. `GeminiAIExtractor` was not implemented.
  4. When `GEMINI_API_KEY` was missing from `.env`, the system gave no error or warning to the user, silently generating duplicate dummy mock invoices.
- **How fixed:**
  1. Implemented `GeminiAIExtractor` in `scanning/services/extraction.py` using `google-genai` multimodal vision, prompt adhering to MASTER_PROMPT Section 7 schema, and robust JSON parsing with code-fence cleanup.
  2. Implemented `ClaudeAIExtractor` fallback for Claude Vision.
  3. Updated `get_ai_extractor(provider=None)` to instantiate the active configured provider and validate that the required API key is present; otherwise raises actionable `AIExtractionError`.
  4. Updated `scanning/views.py` `upload_view` to use dynamic `AI_PROVIDER` from settings, and display an explicit error/warning if the required API key is missing rather than generating deceptive mock bills.
  5. Added warning badge in `scanning/templates/scanning/upload.html` guiding users to set `GEMINI_API_KEY` in `.env`.
- **Regression test:** `tests/test_scanning.py::TestAIExtractorProviderResolution` (6 tests covering provider resolution, missing API key error, warning banner, Gemini extraction, code-fence cleanup, malformed JSON, and API exception handling).

---

## BUG-002: Newly Scanned First-Time Bill Falsely Flagged As Duplicate of Itself

- **Date:** 2026-10-14
- **Reported by:** user
- **Severity:** Medium
- **What happened:** When a user uploaded and scanned a bill for the first time, the document review screen displayed an integrity warning: `"Possible duplicate: Bill with invoice #<invoice_no> and total <total> already exists in the system (Bill #<id>)"`, even though the bill had never been uploaded before.
- **Root cause:** In `scanning/services/extraction.py`, the `Bill` record was saved to the database in Step 3 before `detect_bill_errors(validated_data)` was invoked in Step 5. `detect_bill_errors` performed a duplicate lookup (`Bill.objects.filter(invoice_no=..., grand_total=...)`) without excluding the current bill's PK, causing newly saved bills to match against themselves.
- **How fixed:**
  1. Updated `detect_bill_errors` in `scanning/services/validation.py` to accept an `exclude_bill_id: Optional[int] = None` parameter and check `extracted_data.get("bill_id")`, filtering out the current bill with `.exclude(pk=target_exclude_id)`.
  2. Updated `scanning/services/extraction.py` to pass `exclude_bill_id=bill.pk` when calling `detect_bill_errors`.
- **Regression test:** `tests/test_scanning.py::TestAIExtractorProviderResolution::test_newly_scanned_bill_not_flagged_as_duplicate_of_itself`

---

## BUG-003: Unverified/Pending Scanned Bills Counted in Total Collection and Financial KPIs

- **Date:** 2026-10-14
- **Reported by:** user
- **Severity:** High
- **What happened:** When bills were scanned and awaiting user review (status `NeedsReview` or `Draft`), the system immediately included them in the Total Spend / Total Collection amount, Total Bills count, Average Bill, and credit metrics on the dashboard, distorting financial KPIs before bills were verified and approved.
- **Root cause:** `reports/services.py` queries in `get_spending_summary`, `get_spending_by_category`, `get_top_vendors`, and `get_spending_over_time` filtered only by `is_deleted=False` and `bill_type=PURCHASE`, without checking `status=Bill.Status.VERIFIED`.
- **How fixed:**
  1. Updated all spending KPI functions in `reports/services.py` to filter strictly by `status=Bill.Status.VERIFIED`.
  2. Added separate `pending_count` and `pending_amount` calculations for unverified bills (`NeedsReview` / `Draft`).
  3. Created a dedicated **Pending Review** stat card and notification banner on the dashboard in `templates/dashboard/index.html` displaying pending bills count and amount with a direct link to review them.
- **Regression test:** `tests/test_ledger_reports.py::TestSpendingSummaryCalculations::test_spending_summary_kpi_metrics`

---

## BUG-004: Items with Zero Price (Waived Fees, Free Items) Falsely Flagged as Missing Price

- **Date:** 2026-10-14
- **Reported by:** user
- **Severity:** Medium
- **What happened:** On bills and fee challans where certain line items have 0 amount (e.g. waived fees like "Generator fee: 0", "Annual funds: 0", or complimentary line items), the system bordered them in red, generated `missing_field` errors, showed `⚠️ Item price is missing or 0.00. Grand total may be incomplete`, and blocked one-click verification with `⚠️ Check Total`, even though the bill items balanced and matched the total.
- **Root cause:** Validation logic in `scanning/services/validation.py`, `bills/models.py`, `scanning/views.py`, and `review.html` blindly treated any price `<= 0` as a missing price error without checking whether the total of items already reconciled with the slip total.
- **How fixed:**
  1. Updated `bills/models.py` (`has_missing_price`): an item with 0.00 price is not treated as missing unless its price is truly blank/None, explicitly named missing, or there is a shortfall between the items sum and the invoice total.
  2. Updated `scanning/services/validation.py` (`detect_bill_errors`): precomputes target subtotal and checks for a shortfall before flagging zero prices.
  3. Updated `scanning/views.py` (`review_view`): evaluates `has_missing_price` accounting for shortfall and explicit missing markers.
  4. Updated `scanning/templates/scanning/review.html`: only highlights empty/blank price inputs in red (`priceVal === ''`) or items causing a shortfall, and updated hint copy to `⚠️ Item price is missing. Grand total may be incomplete`.
  5. Cleared stale `missing_field` error records on affected bills (e.g. Bill 48).
- **Regression test:** `tests/test_scanning.py::TestAIExtractorProviderResolution::test_zero_price_items_not_treated_as_missing_when_total_matches`

---

## BUG-005: Empty Arrears Row Misattributed with Grand Total on Fee Challan

- **Date:** 2026-10-15
- **Reported by:** user
- **Severity:** Medium
- **What happened:** On pre-printed school fee challans (e.g. Challan #1707 / Bill #64), the `Arreras` (Arrears) line was blank on the paper slip, with `Annual funds: 5000` and the bottom summary row `Grand Total: 5000`. The AI model mistakenly attributed the Grand Total `5000` into `Arreras`, doubling the extracted items total to 10,000 and triggering a calculation discrepancy error.
- **Root cause:** Because `Arreras` is physically printed directly above `Grand Total`, the OCR vision model grouped the Grand Total amount `5000` into both `Arreras` and `Grand Total`.
- **How fixed:**
  1. Updated `EXTRACTION_SYSTEM_PROMPT` in `scanning/services/extraction.py` with Rule 16: pre-printed forms and fee challans with blank cells must be extracted as `0.0`, and the bottom summary `Grand Total` line must never be assigned to the fee row directly above it.
  2. Implemented Rule 16 post-processing in `validate_extraction_schema`: when `grand_total > 0` and `items_sum > grand_total`, if resetting a blank-prone fee item (such as `arrears`, `arreras`, `others`, `late fee`) that duplicate-matched the Grand Total to `0.0` reconciles the items sum to match `grand_total`, it is normalized to `0.0` and subtotal is recalculated.
  3. Cleaned up Bill #64 and ScanJob #64 in the database so `Arreras` has `0.00`, `subtotal` = 5000.00, `grand_total` = 5000.00, and false discrepancy errors are cleared.
- **Regression test:** `tests/test_scanning.py::TestAIExtractorProviderResolution::test_fee_challan_blank_arrears_row_not_assigned_grand_total`

---

## BUG-006: Duplicate Bill Not Detected Pre-Extraction Due to Raw Client Hash vs Pillow JPEG Recompression Hash Mismatch

- **Date:** 2026-10-15
- **Reported by:** user
- **Severity:** High
- **What happened:** When a user selected or uploaded an identical bill that had already been scanned previously (e.g. `WhatsApp_Image_2026-10-14_at_11.57.00_PM.jpeg`), the system displayed no duplicate warning on the upload screen. Submitting the form triggered a redundant AI scan and generated a duplicate bill (#68 alongside #55) instead of detecting the duplicate before processing.
- **Root cause:** 
  1. In `scanning/services/image_processing.py`, `validate_and_preprocess_file()` calculated `hasher = hashlib.sha256(processed_bytes)` after Pillow JPEG recompression (`quality=85`), storing the processed bytes hash in `BillFile.file_hash`. In contrast, the browser calculated `crypto.subtle.digest('SHA-256', buffer)` on the raw uncompressed client file. Because `raw_client_hash != pillow_processed_hash`, `/scanning/check-duplicate/?hash=...` queries never matched.
  2. `check_duplicate_view()` in `scanning/views.py` only checked `file_hash` and lacked a fallback for legacy records.
  3. `checkDuplicateFile()` in `upload.html` hardcoded `/en/scanning/check-duplicate/`, which failed to adapt to Urdu localized routes (`/ur/`).
  4. `upload_view()` in `scanning/views.py` lacked a server-side pre-scan duplicate gate, creating redundant ScanJobs and spending AI API tokens on duplicates if submitted.
- **How fixed:**
  1. Updated `scanning/services/image_processing.py` to calculate and return `raw_hash = hashlib.sha256(content_bytes).hexdigest()`, guaranteeing that client-side SHA-256 and server-side hashes match identically.
  2. Added indexed `raw_hash` field to `BillFile` in `scanning/models.py` (migration `0002_billfile_raw_hash_alter_billfile_file_hash.py`) and backfilled existing database records.
  3. Updated `check_duplicate_view` in `scanning/views.py` to query `Q(raw_hash=file_hash) | Q(file_hash=file_hash)` with filename fallback, and fixed reverse URL pattern to `bills:bill_detail`.
  4. Added server-side Pre-Scan Duplicate Gate in `upload_view`: halts processing before creating `ScanJob` or invoking AI, rendering a warning banner with "View Existing Bill" and "Scan Anyway as New Bill".
  5. Updated `upload.html` with localized dynamic `checkUrl = "{% url 'scanning:check_duplicate' %}"`, passing `name` and `size`, prominent client-side duplicate alert banner, card-level `DUPLICATE / ڈپلیکیٹ` badge, and server-side duplicate alert block.
- **Regression test:** 
  - `tests/test_scanning.py::TestAIExtractorProviderResolution::test_client_raw_file_hash_matches_preprocessed_file_duplicate_check`
  - `tests/test_scanning.py::TestAIExtractorProviderResolution::test_upload_post_pre_scan_duplicate_gate_blocks_redundant_scan`

---

## BUG-007: 403 Forbidden When Staff User Without Delete Permission Attempted to Delete Bill

- **Date:** 2026-10-16
- **Reported by:** user
- **Severity:** Medium
- **What happened:** When reviewing bills awaiting verification, a user attempted to delete an unwanted pending bill (#69) via the bill list table's "Delete" link (`/bills/69/delete/`) and received an unstyled HTTP 403 Forbidden error screen.
- **Root cause:** 
  1. The user was logged in with a staff account (`demo`) which was initially created without the `can_delete_records` permission flag.
  2. `bills/templates/bills/bill_list.html` unconditionally rendered the "Trash" header link and the per-row "Delete" button to all authenticated users, without checking `request.user.can_delete_records` or superadmin privileges.
  3. No custom `403.html` template existed in the application, causing Django to render a bare, confusing 403 Forbidden page without explaining why permission was denied or how to resolve it.
- **How fixed:**
  1. Updated the production database to grant `can_delete_records=True`, `can_manage_shop=True`, and `can_manage_categories=True` to the `demo` staff account.
  2. In `bills/templates/bills/bill_list.html`, conditionally wrapped the "Trash" header link and the row-level "Delete" action button inside `{% if request.user.is_superuser or request.user.is_superadmin or request.user.can_delete_records %}` so unpermitted staff are not presented with actions they cannot perform.
  3. Created `templates/403.html` with a user-friendly, responsive bilingual (English + Urdu) design explaining that the user account lacks the required permission, providing a staff permission guide, and offering one-click navigation back to Bills or Dashboard.
- **Regression test:** 
  - `tests/test_bills.py::TestBillSoftDeleteAndTrash::test_bill_list_view_hides_delete_and_trash_for_staff_without_permission`
  - `tests/test_bills.py::TestBillSoftDeleteAndTrash::test_bill_list_view_shows_delete_and_trash_for_permitted_staff`
  - `tests/test_bills.py::TestBillSoftDeleteAndTrash::test_forbidden_delete_renders_403_page`



