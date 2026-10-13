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

## Risk Log

| Risk | Mitigation |
|------|-----------|
| AI extraction accuracy on handwritten bills | Golden Bills test set catches regressions early |
| Free-tier limits (Render sleeping, Cloudinary storage) | Documented workarounds in Security/DevOps agent |

---

## Bug Log
See [`docs/BUG_LOG.md`](./BUG_LOG.md)
