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

---

## BUG-008: Bill Selection Dropdown Showed Other Parties' Bills Resulting in '__all__: Bill party does not match payment party'

- **Date:** 2026-10-17
- **Reported by:** user
- **Severity:** High
- **What happened:** When recording a payment against a party (e.g. `/en/ledger/payments/add/?party=31` for "ABRISH ASIF"), the "Associated Bill / Invoice" dropdown listed bills belonging to completely different vendors/customers (such as Bill 1708 belonging to "Rah-e-Danish..."). Selecting any bill not belonging to the chosen party caused form submission to fail with an ugly raw error: `• __all__: Bill party does not match payment party.`.
- **Root cause:** 
  1. `PaymentForm` in `ledger/forms.py` did not filter the `bill` queryset by the selected `party_id`, rendering all system bills across all parties in the dropdown.
  2. `PaymentForm` lacked a `clean()` method validating that `bill.party == party`, so the error was only raised inside `record_payment()` service after form validation.
  3. `payment_add_view` caught `ValidationError` from `record_payment()` and attached it to `None`, which Django assigns to `__all__`.
  4. `payment_form.html` displayed `form.errors.items` with raw `<li>{{ field }}: {{ error }}</li>`, displaying `__all__:` verbatim to the end user.
  5. The template lacked client-side dynamic filtering to update available bills when switching between parties.
- **How fixed:**
  1. Updated `PaymentForm` (`ledger/forms.py`):
     - Scopes `bill` queryset by `party_id` when `party` is provided in form submission, initial data, or instance.
     - Implemented `PaymentForm.clean()` to validate that the selected bill belongs to the chosen party, attaching error directly to `bill`.
     - Formatted bill option labels to show invoice number and due balance (e.g., `#1708 — Due: PKR 2,500.00 (Total: 2,500.00)`).
  2. Updated `payment_add_view` (`ledger/views.py`):
     - Added support for `?bill=<id>` parameter, automatically pre-filling the bill's party and remaining balance due into the form.
     - Injects `bills_data` JSON into the template context for instantaneous client-side reactive filtering.
     - Routes service `ValidationError` on party mismatch specifically to the `bill` field.
  3. Updated `payment_form.html` (`ledger/templates/ledger/payment_form.html`):
     - Sanitized form error banner so `__all__:` is never printed.
     - Added client-side JavaScript that immediately updates the bill dropdown whenever the party changes.
     - If the party has no bills (like Party 31), displays: `No open bills for this party (will record on-account)` with an informative badge and helper note explaining that the payment will be credited directly to their running ledger (Khata).
     - Selecting a bill auto-fills the payment amount with the bill's balance due.
- **Regression test:** 
  - `tests/test_payments.py::TestPaymentViewsAndEndpoints::test_payment_form_rejects_bill_belonging_to_different_party`
  - `tests/test_payments.py::TestPaymentViewsAndEndpoints::test_payment_add_view_mismatched_bill_does_not_render_raw_all_error`

---

## BUG-009: SaaS Console Displayed Mock Dummy Data for New Tenants & Demo Account Login Failed

- **Date:** 2026-10-17
- **Reported by:** user
- **Severity:** High
- **What happened:**
  1. When superadmin viewed the SaaS Console (`/en/accounts/superadmin/`), `demo1` was displayed with mock dummy data (`Lahore Autos & Spares`, `orders@lahoreautos.pk`, fake `Pro` tier, fake `42 / 100 scans` used) alongside an artificially inflated dummy tenant (`Karachi Cash & Carry`).
  2. The `demo` account failed to log in.
  3. When new tenants registered via self-service onboarding, `register_owner_user` saved the business name only into `first_name`, leaving `user.business_name` blank.
  4. Superadmin had no direct method within the SaaS console to provision new tenant accounts without logging out.
- **Root cause:** 
  1. `demo1` was previously seeded in `db.sqlite3` with mock dummy data from previous development rather than clean tenant defaults.
  2. `demo`'s database password was set to `demo123` instead of the expected `demo`.
  3. `register_owner_user()` in `accounts/services.py` omitted `business_name=business_name`.
  4. SaaS console header linked to `/accounts/register/`, which redirected logged-in superadmins to the dashboard, blocking them from adding new tenants directly.
- **How fixed:**
  1. Cleaned up `demo` and `demo1` in the database to reflect authentic tenant profiles (`demo` with password `demo`, `demo1` with password `demo1`, 0 scans used, 10 free scans quota), and removed the dummy `karachi_cash_carry` mock record.
  2. Updated `register_owner_user()` in `accounts/services.py` to persist `business_name`, `plan`, and `monthly_scan_quota`.
  3. Added `superadmin_create_tenant_view` in `accounts/views.py` and `superadmin_create_tenant` URL in `accounts/urls.py` allowing superadmins to provision new tenants directly from the console.
  4. Added `+ Add New Tenant` modal (`createTenantModalOpen`) directly inside `templates/accounts/superadmin_dashboard.html`.
- **Regression test:** 
  - `tests/test_saas_landing_and_registration.py::TestSaaSSelfServiceRegistration::test_successful_registration_creates_user_and_logs_in`
  - `tests/test_superadmin_dashboard.py::TestSuperadminTenantActions::test_superadmin_can_create_new_tenant`

---

## BUG-010: Staff Management, Landing Settings, and Reset Data Tabs Were Visible to Tenant Accounts

- **Date:** 2026-10-17
- **Reported by:** user
- **Severity:** High
- **What happened:** When tenant user `demo` logged into their shop account and visited Settings (`/en/settings/`), the sub-navigation bar displayed platform-level administration tabs: "Staff Management" (listing all system accounts including superadmins, other tenants, and allowing password resets), "Landing Page & Marketing", and "Reset App Data". In addition, tenant accounts displayed a "Super Admin" badge next to their username.
- **Root cause:** 
  1. `templates/settings_app/settings_base.html` used `{% if request.user.is_superuser or request.user.is_superadmin or request.user.role == 'superadmin' %}` for Staff Management, Landing Settings, and Reset App Data.
  2. Because self-service onboarding assigned `role=User.Role.SUPERADMIN` (intended for in-store authority before SaaS multi-tenancy), tenants matched the condition and saw global platform management tabs.
  3. The `superadmin_required` decorators in `accounts/views.py` and `settings_app/views.py` allowed access if `user.role == 'superadmin'`, permitting non-superusers to access `/en/settings/staff/`, `/en/settings/landing/`, and `/en/settings/reset/`.
  4. `templates/base.html` displayed a purple "Super Admin" badge for any account where `request.user.is_superadmin` was True.
- **How fixed:**
  1. Updated `templates/settings_app/settings_base.html` so that "Staff Management", "Landing Page & Marketing", and "Reset App Data" are guarded strictly by `{% if request.user.is_superuser %}`.
  2. Converted template comments for those tabs into Django comments (`{# ... #}`) inside the `{% if %}` blocks to ensure no comment artifacts leak into the rendered HTML.
  3. Hardened `superadmin_required` in both `accounts/views.py` and `settings_app/views.py` to check `if not user.is_superuser: return HttpResponseForbidden(...)`.
  4. Updated `templates/base.html` role badge logic: superusers display a purple "Super Admin" badge; tenant business accounts display a blue/green "Business Owner" badge; staff display a "Staff" badge.
- **Regression test:** 
  - `tests/test_staff_management.py::TestStaffListView::test_tenant_user_denied_access_to_staff_list`
  - `tests/test_settings_ui.py::TestSettingsSubNavigationAndShell::test_staff_management_tab_hidden_for_tenant`
  - `tests/test_settings_ui.py::TestSettingsSubNavigationAndShell::test_reset_data_tab_visible_only_for_superadmin`





