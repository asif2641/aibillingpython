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

