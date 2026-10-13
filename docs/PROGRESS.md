# Bill Scanner & Ledger — Progress Tracker

> Updated by the Lead Architect. Source of truth for what is done, in progress, blocked, and at risk.

---

## Phase 1 — Foundation

**Branch:** `phase-1/foundation`  
**Status:** ✅ Complete (Passed Quality Gate with 69/69 tests, 93% coverage)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1 | Project scaffolding & environment setup | Backend Agent | ✅ Done | Django apps, settings, tests, README |
| 2 | Custom User model, roles & auth | Backend Agent | ✅ Done | 5-attempt lockout, forms, services, admin |
| 3 | Base dashboard layout (shell) | Frontend Agent | ✅ Done | Responsive sidebar, topbar, cards, mobile nav |
| 4 | English ↔ Urdu / RTL | Frontend Agent | ✅ Done | Full Urdu translations (.po/.mo) & RTL layout |
| 5 | Light / dark theme | Frontend Agent | ✅ Done | Tailwind dark mode with localStorage toggle |
| 6 | QA — write Phase 1 tests | QA Agent | ✅ Done | 69 tests passing with 93% coverage |
| 7 | QC review & Gate Report | QC + Browser QA | ✅ Done | APPROVED with 0 Critical/High issues |

---

## Phase 2 — Settings (Shop Profile, Staff Permissions, Categories, Units)

**Branch:** `phase-2/settings`  
**Status:** ✅ Complete (Passed Quality Gate with 145/145 tests, 93% coverage)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1 | Shop Profile model & service | Backend Agent | ✅ Done | Singleton ShopProfile with limits, tax ID |
| 2 | Staff Management & permissions | Backend Agent | ✅ Done | Staff creation, permission flags, reset pass |
| 3 | Categories & Units models & seeding | Backend Agent | ✅ Done | 10 default categories & 9 units seeded |
| 4 | QA test-first suites for Phase 2 | QA Agent | ✅ Done | 67 comprehensive test cases written |
| 5 | Settings & Staff UI templates | Frontend Agent | ✅ Done | Unified settings subnav, RTL, dark theme |
| 6 | QC review & Gate Report | QC + Browser QA | ✅ Done | APPROVED with 0 Critical/High issues |

---

## Phase 3 — Manual Bills (Entry Form, Bill List, Edit, Trash, Parties, Payments)

**Branch:** `phase-3/manual-bills`  
**Status:** ✅ Complete (Passed Quality Gate with 251/251 tests, 95% coverage)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1 | Parties model & service (Vendors & Customers) | Backend Agent | ✅ Done | Fuzzy matching, type filtering, Urdu support |
| 2 | Bill & BillItem models, recalculation & trash | Backend Agent | ✅ Done | Zero float money math, soft delete trash pattern |
| 3 | Payment model & recording service | Backend Agent | ✅ Done | Payment recording, status transitions, balance tracking |
| 4 | QA test-first suites for Phase 3 | QA Agent | ✅ Done | 95 new comprehensive automated tests |
| 5 | Manual bill entry, roster & party UI templates | Frontend Agent | ✅ Done | Responsive forms, line items formset, RTL, dark theme |
| 6 | QC review & Gate Report | QC + Browser QA | ✅ Done | APPROVED with 0 Critical/High issues |

---

## Phase 4 — AI Scanning (Document Upload, Gemini/Claude Vision Pipeline, Review & Correction Screen)

**Branch:** `phase-4/ai-scanning`  
**Status:** ✅ Complete (Passed Quality Gate with 276/276 tests, 94% coverage)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1 | Scanning data models (BillFile, ScanJob, BillError, BillEditHistory) | AI Extraction Agent | ✅ Done | Document tracking, token logging, error models |
| 2 | Provider-agnostic AI extraction engine & Mock provider | AI Extraction Agent | ✅ Done | Pillow preprocessing, Section 7 schema, quota limits |
| 3 | Automated error detection & duplicate detection service | AI Extraction Agent | ✅ Done | 7 accounting rules, auto-profiles, category suggestion |
| 4 | QA test-first suites for Phase 4 | QA Agent | ✅ Done | 25 automated unit & integration tests |
| 5 | Bill upload UI with multi-page management | Frontend Agent | ✅ Done | Drag-and-drop, camera trigger, page previews |
| 6 | Split-screen review & correction screen | Frontend Agent | ✅ Done | Original doc viewer, editable form, live math, RTL |
| 7 | QC review & Gate Report | QC + Browser QA | ✅ Done | APPROVED with 0 Critical/High issues |

---

## Phase 5 — Ledger & Reports (Khata, Spending Analytics, Price History & Charts)

**Branch:** `phase-5/ledger-reports`  
**Status:** ✅ Complete (Passed Quality Gate with 299/299 tests, 93% coverage)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1 | Party Ledger (Khata) service & statement generator | Backend Agent | ✅ Done | Chronological timeline, running balance, CSV export |
| 2 | Spending reports & price history tracking services | Backend Agent | ✅ Done | KPIs, category share, vendor rank, price fluctuation |
| 3 | QA test-first suites for Phase 5 | QA Agent | ✅ Done | 23 comprehensive automated tests in test_ledger_reports.py |
| 4 | Interactive Dashboard with Chart.js | Frontend Agent | ✅ Done | Real-time KPIs, spending timeline line chart & donut |
| 5 | Party Ledger statement & printable views | Frontend Agent | ✅ Done | Running balance table, bilingual RTL, dark theme, CSV |
| 6 | Spending reports & price trend UI | Frontend Agent | ✅ Done | Date presets, category share, top vendors, inflation index |
| 7 | QC review & Gate Report | QC + Browser QA | ✅ Done | APPROVED with 0 Critical/High issues |


---

## Phase 6 — Offline PWA & Sync Queue (Installable App, Offline Manual Entry, Conflict Resolution)

**Branch:** `phase-6/offline-pwa`  
**Status:** ✅ Complete (Passed Quality Gate with 345/345 tests, all criteria met)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1 | SyncQueue data model & processing services | Backend Agent | ✅ Done | Idempotent client_id guard, Decimal recalculations, conflict handling |
| 2 | Sync API endpoints (/sync/push/, /sync/pull/, /sync/status/) | Backend Agent | ✅ Done | Authenticated JSON endpoints, i18n + root namespaces |
| 3 | QA test-first suites for Offline Sync & PWA | QA Agent | ✅ Done | 46 automated tests: test_sync.py (29), test_pwa.py (10), test_offline_ui.py (7) |
| 4 | PWA Web Manifest, Service Worker & Offline Shell | Frontend Agent | ✅ Done | manifest.json, sw.js network-first caching, bilingual offline.html |
| 5 | IndexedDB client storage & auto-sync engine | Frontend Agent | ✅ Done | offline-sync.js (607 lines), form interception, auto-sync on reconnect, Urdu RTL |
| 6 | QC review & Gate Report | QC + Browser QA | ✅ Done | APPROVED — all 9 QC criteria passed, 0 Critical/High issues |

---

## Phase 7 — Polish & Security (Responsive/Mobile Polish, Performance, Activity Log, Backups)

**Branch:** `phase-7/polish-security`  
**Status:** ⏳ In Progress

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1 | `purge_sync_queue` management command (>30 days cleanup) | Backend Agent | [ ] Not started | QC non-blocking recommendation from Phase 6 |
| 2 | `?since=` delta sync in offline-sync.js (store last_pulled_at in IndexedDB) | Frontend Agent | [ ] Not started | QC non-blocking recommendation from Phase 6 |
| 3 | Activity log model & middleware (audit trail) | Backend Agent | [ ] Not started | Track bill creation, edits, deletions per user |
| 4 | Mobile responsiveness polish (tables → cards on phones) | Frontend Agent | [ ] Not started | Bills list, ledger, reports → card layout on mobile |
| 5 | Performance hardening (DB indexes, dashboard caching) | Backend Agent | [ ] Not started | Index on bill_date, party, status; cache dashboard KPIs |
| 6 | Security hardening (rate limiting, security headers, signed URLs) | Security/DevOps Agent | [ ] Not started | django-ratelimit on scan, X-Frame-Options, CSP header |
| 7 | Automated backup management command | Security/DevOps Agent | [ ] Not started | `python manage.py backup_db` with retention policy |
| 8 | QA test-first suites for Phase 7 | QA Agent | [ ] Not started | Tests for activity log, purge command, security headers |
| 9 | QC review & Gate Report | QC + Browser QA | [ ] Not started | Final quality audit before Phase 8 (Deployment) |

---

## Risk Log

| Risk | Mitigation |
|------|-----------|
| AI extraction accuracy on handwritten bills | Golden Bills test set catches regressions early |
| Free-tier limits (Render sleeping, Cloudinary storage) | Documented workarounds in Security/DevOps agent |

---

## Bug Log
See [`docs/BUG_LOG.md`](./BUG_LOG.md)
