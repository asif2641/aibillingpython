# Bill Scanner & Ledger App — Master Prompt

> This document is the **single source of truth** for what to build.
> All agents must read this before starting any task. Never invent features not described here.

---

## Part 1 — Product Requirements

### 0. Your Role and Working Rules

You are a senior full-stack engineer, product designer and patient teacher.
The product owner is a complete beginner with no coding or database experience.
Build this product from scratch, step by step.

Rules you must follow:
1. Work in phases (Section 15). Finish one phase, tell the owner how to run and test it, and wait for "continue" before starting the next.
2. Give exact copy-paste commands for every setup step (Windows first, also Mac/Linux). Explain in one simple sentence what each command does.
3. Never assume the owner knows a term. Explain it in plain words the first time.
4. Write clean, commented, well-organized code. No placeholders like "add your code here". Every file must be complete.
5. Keep secrets (API keys, passwords) in a `.env` file. Never hard-code them.
6. If something is unclear or risky, ask one short question before building.
7. After each phase give: (a) what was built, (b) how to run it, (c) a test checklist, (d) what comes next.
8. If an error appears, explain the cause simply and give the fix.

### 1. Product Summary

A responsive web app in dashboard style where a user uploads a bill (photo, screenshot or PDF; printed or handwritten). AI reads the bill and extracts all information automatically, creates shopkeeper (vendor) and customer profiles, files the bill under a category, and gives full spending reports, charts and a payment ledger. Works in English (default) and Urdu. Manual entry works offline and syncs later.

### 2. Technology Stack

- **Language:** Python 3.11+
- **Framework:** Django (login, user roles, admin, security, translation (i18n) and database tools built in)
- **Frontend:** Django templates + Tailwind CSS + HTMX + Alpine.js. Chart.js for charts.
- **Offline support:** Progressive Web App (PWA): service worker + IndexedDB queue that syncs when internet returns.
- **Database:** SQLite (local) / PostgreSQL via `DATABASE_URL` env var (hosted)
- **AI bill reading:** Vision-capable AI model API (Google Gemini free tier or Claude API) behind a provider-agnostic wrapper. Must read handwritten and printed bills in English, Urdu and mixed text. Optional fallback: PDF text extraction (PyMuPDF) for digital PDFs.
- **File storage:** local `media/` folder in dev; Cloudinary or Supabase Storage in hosted stages.
- **Background processing:** Django-Q2 or Celery-free alternative. Show a progress state (never freeze the page). Workers and pipelines must maintain dedicated, isolated database sessions (`close_old_connections()` in Django / `SessionLocal()` in SQLAlchemy) rather than inheriting request-scoped connections that close upon HTTP response return.
- **Auth:** Django auth with custom roles.
- **Hosting stages:** (1) local computer, (2) free server (Render), (3) live server (low-cost VPS or paid plan).

### 3. Users and Roles

| Role | Can do |
|------|--------|
| **Super Admin** | Everything. Creates/manages staff accounts, edits shop profile, categories, language defaults, deletes data, sees all reports. |
| **Staff** | Upload/scan bills, add manual bills, edit bills, view customers/vendors/reports. Cannot manage staff, change shop profile, or delete data (Super Admin can enable these per staff member with permission checkboxes). |

- Login with username + password. Passwords hashed.
- Lock account for 15 minutes after 5 wrong attempts.
- Super Admin can reset staff passwords and disable accounts.

### 4. Core Features (build all)

#### 4.1 Bill Upload
- Upload image (JPG, PNG, HEIC, WEBP), screenshot or PDF, by file picker, drag-and-drop, or camera capture on mobile.
- **Multi-page bills:** one bill can have many files, labelled Image 1, 2, 3 … and PDF pages. User can reorder, remove or add pages before scanning. AI treats all pages as one bill and merges items without duplicates.
- Auto image cleanup before scanning: rotate/deskew, resize, improve contrast, compress. Reject files over 15 MB or unsupported types with a friendly message.
- **Pre-AI Document Quality Assessment (Quality Gate):**
  - Minimum Resolution Guard: Reject images under 100×100 pixels.
  - Blurry Image Detection: Measure edge variance and sharpness ratio to flag out-of-focus or blurred bills.
  - Low Light / Dark Image Detection: Compute mean luminance (< 35/255) to catch underexposed/dark photos.
  - Blank Page Detection: Measure contrast stddev (< 3.5) to catch empty pages or uniform sheets.
  - Pre-flight Alerts: Client-side badges on upload preview tiles + server-side validation in `validate_and_preprocess_file` before creating ScanJobs or spending AI tokens. Full Urdu and English bilingual feedback.
- **Direct Mobile Camera Capture Shortcut:**
  - Dedicated "Take Photo" button with `<input type="file" accept="image/*" capture="environment">` to trigger the device back camera directly on phones without digging into gallery pickers.
  - Multi-page camera snapping tile ("Camera / کیمرہ سے اگلا صفحہ") in document roster.
  - Auto-open camera via `?camera=1` query parameter from mobile dashboard and bottom navigation bar.
- **Background Pipeline & Database Session Isolation:**
  - Background extraction tasks must maintain an isolated database connection/session lifecycle (e.g. `SessionLocal()` with explicit `try / finally db.close()` or Django's `close_old_connections()`).
  - Never reuse request-scoped database sessions that terminate upon HTTP response return, eliminating race conditions and closed session connection errors under concurrent uploads.
- Show upload preview and a progress indicator.

#### 4.2 AI Extraction (no fixed template)
The AI must work on any bill layout (shop receipt, invoice, handwritten note, thermal slip, utility bill, screenshot). Extract:
- **Header:** shop/company name, shop address, phone, tax/NTN/GST number, customer name, customer phone/address (if present), invoice/bill number, date, time.
- **Line items:** serial no., item name, description, quantity, unit, unit price, discount, tax, line total.
- **Footer:** subtotal, discount, tax/GST, delivery/other charges, round-off, grand total, amount paid, balance due, payment method.
- **Meta:** detected language(s), detected category, currency, confidence score per field (0–100), handwritten/printed flag.
- Return strict JSON following the schema in Section 7. If a field is missing, return `null`—never guess.
- Keep original uploaded files linked to the bill forever.

#### 4.3 Auto-Profiles
- After scanning, automatically create or match a Shopkeeper (Vendor) profile using fuzzy matching. If unsure, show "Is this the same as …?" for user confirmation.
- Same for Customer profile.
- Profile page: name, contact, address, notes, total bills, total amount, first/last bill date, all their bills.
- Bill type toggle: **Purchase** (bought from vendor) / **Sale** (sold to customer).

#### 4.4 Review, Error Detection and Editing
After scanning, show Review screen: original image on one side, editable extracted data on the other, low-confidence fields highlighted yellow/orange.

Auto-flag errors:
- `quantity × unit price ≠ line total`
- `sum of line totals ≠ subtotal`; `subtotal − discount + tax ≠ grand total`
- Missing date, invoice number, grand total
- Future date or date far in the past
- Unit looks wrong for the item
- Possible duplicate bill (same vendor + invoice no. + total + date)
- Negative or zero values, unreadable text

Each error shows a plain message with a "Fix" button. Users can edit any field, add/delete item rows; totals recalculate live. Keep edit history (who changed what and when). Bill statuses: **Draft → Needs Review → Verified**.

#### 4.5 Manual Bill Entry (online and offline)
- Fast form: vendor/customer (search or create), date, time, invoice no., category, items (name, quantity, unit, price, auto line total), discount, tax, grand total, payment status, notes, optional photo.
- **Offline:** form still works, saves to IndexedDB. Show "Offline – will sync" badge. Auto-sync on reconnect, handle conflicts safely, never lose data.

#### 4.6 Views, Reports and Charts
Dashboard with date filter (Today, 7 days, This month, Last month, This year, Custom range):
- Cards: total spent, total bills, average bill, top vendor, top category, outstanding credit.
- Charts: spending over time (line), spending by category (donut), top 10 vendors (bar), monthly comparison (bar), price trend of selected item (line), payment status (paid vs credit).

Pages: All Bills, All Vendors, All Customers, Spending Reports, Repeat Purchases & Price History, Item Search.

#### 4.7 Categories
- AI auto-detects category per bill (Grocery, Medical, Utilities, Fuel, Electronics, Clothing, Restaurant, Construction, Stationery, Other).
- User can change the suggestion. AI learns from corrections via vendor→category mappings.
- Super Admin: add, rename, merge, color-code and archive categories.

#### 4.8 Vendor/Customer Ledger (Khata)
- Per party: Total bill amount, Total paid, Total received, Credit/Balance due, full ledger statement.
- Record payments against a party or specific bill (partial payments allowed). Auto-update bill status: Unpaid / Partially Paid / Paid.
- Labels: "You owe" and "You will receive". Export as PDF/Excel.
- Dashboard widget: top pending balances, overdue items.

#### 4.9 Settings
- Shop Profile: name, logo, address, phone, email, tax number, currency, time zone, date format, default language, invoice footer text.
- Staff Management (Super Admin only): create/disable/reset staff.
- Categories management, Units list, AI settings (provider choice, strict/lenient mode), Data backup/export, Language switcher.
- Activity log.

### 5. Multi-Language
- Full UI translation: English (default) and Urdu. Use Django i18n.
- Urdu = RTL layout. Use Noto Sans Arabic for body text.
- Language switcher in top bar; remember per user.
- AI must read Urdu, English and mixed scripts. Store extracted text as-is; keep an English-normalized item name for reports.

### 6. Data Model

Tables: `User` (role, permissions) · `ShopProfile` · `Party` (type: vendor/customer/both) · `Bill` (type: purchase/sale, status: Draft/NeedsReview/Verified, source: scan/manual) · `BillFile` · `BillItem` · `Category` · `Payment` · `BillEditHistory` · `BillError` · `ScanJob` · `ActivityLog` · `SyncQueue`.

Indexes on: `bill_date`, `party`, `category`, `invoice_no`, `normalized_name`. Use `DecimalField` for all money. Soft delete (trash + restore) for bills.

### 7. AI Extraction JSON Schema

```json
{
  "document_type": "printed|handwritten|mixed",
  "languages": ["en", "ur"],
  "vendor": {"name": null, "phone": null, "address": null, "tax_no": null},
  "customer": {"name": null, "phone": null, "address": null},
  "invoice_no": null,
  "date": "YYYY-MM-DD",
  "time": "HH:MM",
  "currency": null,
  "items": [
    {
      "serial_no": 1,
      "name": "",
      "quantity": 0,
      "unit": "",
      "unit_price": 0,
      "discount": 0,
      "tax": 0,
      "line_total": 0,
      "confidence": 0
    }
  ],
  "subtotal": null,
  "discount": null,
  "tax": null,
  "other_charges": null,
  "grand_total": null,
  "paid_amount": null,
  "balance_due": null,
  "payment_method": null,
  "suggested_category": "",
  "field_confidence": {"vendor_name": 0, "date": 0, "grand_total": 0},
  "warnings": []
}
```

Rules: never invent data; use `null` when unreadable; keep original script; preserve every row in order; for multi-page bills merge as one; report uncertainty in `warnings`. Validate JSON with Pydantic, retry once on invalid output. Log token/cost per scan. Enforce daily/monthly scan limits.

### 8. UI / UX Requirements
- Collapsible left sidebar: Dashboard, Scan Bill, Add Bill, Bills, Vendors, Customers, Items, Reports, Ledger, Categories, Settings.
- Top bar: search, language, theme, profile.
- Clean, modern, premium look: consistent spacing, soft shadows, rounded corners, one primary accent colour, light and dark mode, micro-animations, skeleton loaders, empty-state illustrations, friendly toasts, confirmation dialogs.
- Fully responsive, mobile-first. On phones: bottom nav bar, tables become cards, big "Scan Bill" button always reachable.
- Max 3 clicks to any main task. Tooltips, inline validation, keyboard-friendly, accessible contrast, large touch targets.

### 9. Security and Privacy
HTTPS in production · password hashing · CSRF/XSS/SQL-injection protection · role checks on every page and API · rate limiting on login and scan · validate file type by content (not only extension) · private file URLs (signed, expiring) · secrets only in `.env` · automatic database backups · privacy notice that bills are sent to AI provider.

### 10. Performance and Reliability
Background scanning with live status · retry on provider failure · graceful messages when AI quota is exhausted · image compression · database indexes · caching for dashboard numbers · error logging (Sentry free tier optional) · automated tests for calculations, matching, error detection and permissions.

### 11. Deployment Plan (3 stages)
1. **Local:** SQLite, `python manage.py runserver`, open `http://127.0.0.1:8000`.
2. **Free server:** Render + Neon/Supabase PostgreSQL + Cloudinary/Supabase Storage.
3. **Live server:** paid/low-cost server, custom domain, HTTPS, Gunicorn + Nginx, production settings, automatic backups.

### 12. Project Structure
Django apps: `accounts`, `shop`, `parties`, `bills`, `scanning`, `ledger`, `reports`, `categories`, `settings_app`, `sync`. Include `requirements.txt`, `.env.example`, `README.md`, `.gitignore`, `docs/`.

### 13. Extra Features (small but valuable)
Global search · bill tags and notes · duplicate detection · trash/restore · export all data · print bill view · due-date reminders · low-confidence warnings · bulk upload · keyboard shortcuts · scan history with reprocess button.

### 14. Out of Scope for Version 1
Native mobile apps, accounting-software integration, multi-branch companies, barcode inventory, online payments.

### 15. Build Phases (stop and wait after each)

| Phase | Name | Scope |
|-------|------|-------|
| 1 | **Foundation** | Install guide, project setup, database, login, roles, Super Admin, base dashboard layout, English/Urdu switch with RTL, light/dark theme. |
| 2 | **Settings** | Shop profile, staff creation with permissions, categories, units. |
| 3 | **Manual Bills** | Manual entry form, bill list, edit, delete/trash, vendors/customers, payments. |
| 4 | **AI Scanning** | Upload (single + multi-image/PDF), image cleanup, AI extraction, review screen, error detection, auto-profiles, auto-category. |
| 5 | **Ledger & Reports** | Vendor/customer ledger, spending reports, repeat-purchase & price-history, all charts, exports. |
| 6 | **Offline PWA** | Installable app, offline manual entry, sync queue, conflict handling. |
| 7 | **Polish & Security** | Responsive/mobile polish, performance, tests, backups, activity log. |
| 8 | **Deployment** | Free server deployment, then live server deployment guide. |

### 16. Definition of Done
- Scanned printed and handwritten bills both extract correctly with editable results.
- A 3-page bill uploaded as Image 1, 2, 3 becomes one bill.
- Wrong totals are flagged with a fix option.
- Vendor and customer profiles are created automatically and can be marked Customer/Vendor.
- Date-wise and bill-wise totals, charts, repeat-purchase price history and ledger all match underlying bills.
- App works fully in English and Urdu (RTL).
- Manual bill added offline appears on the server after reconnecting.
- Staff can only do what Super Admin allowed.
- Same code runs locally, on the free server, and on the live server.
