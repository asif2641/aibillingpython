# Bill Scanner & Ledger — Progress Tracker

> Updated by the Lead Architect. Source of truth for what is done, in progress, blocked, and at risk.

---

## Phase 1 — Foundation

**Branch:** `phase-1/foundation`  
**Status:** 🚀 In Progress

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1 | Project scaffolding & environment setup | Backend Agent | ✅ Done | Django apps, settings, tests, README |
| 2 | Custom User model, roles & auth | Backend Agent | 🔄 In Progress | Ready for Group A |
| 3 | Base dashboard layout (shell) | Frontend Agent | 🔄 In Progress | Ready for Group A |
| 4 | English ↔ Urdu / RTL | Frontend Agent | ⏳ Waiting | After Task 3 |
| 5 | Light / dark theme | Frontend Agent | ⏳ Waiting | After Task 3 |
| 6 | QA — write Phase 1 tests | QA Agent | 🔄 In Progress | Ready for Group A |
| 7 | QC review & Gate Report | QC + Browser QA | ⏳ Waiting | After Tasks 2-6 |

---

## Risk Log

| Risk | Mitigation |
|------|-----------|
| AI extraction accuracy on handwritten bills | Golden Bills test set catches regressions early |
| Free-tier limits (Render sleeping, Cloudinary storage) | Documented workarounds in Security/DevOps agent |

---

## Bug Log
See [`docs/BUG_LOG.md`](./BUG_LOG.md)
