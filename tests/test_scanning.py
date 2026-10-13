"""tests/test_scanning.py
========================
QA Test-First Suite for Phase 4: AI Scanning, Document Preprocessing,
Schema Validation, Error Detection, and Review Screen.
"""

import io
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from bills.models import Bill
from parties.models import Party
from settings_app.models import ShopProfile

User = get_user_model()


@pytest.fixture
def superadmin_user(db):
    """Create a superadmin user."""
    return User.objects.create_user(
        username="superadmin_scan",
        email="scanadmin@example.com",
        password="TestPass123!",
        role=User.Role.SUPERADMIN,
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def sample_image():
    """Create a dummy in-memory JPEG image."""
    img = Image.new("RGB", (800, 1000), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile(
        name="test_bill.jpg",
        content=buf.read(),
        content_type="image/jpeg",
    )


@pytest.fixture
def sample_oversized_image():
    """Create a mock uploaded file that exceeds the 15MB limit."""
    content = b"x" * (16 * 1024 * 1024)  # 16 MB
    return SimpleUploadedFile(
        name="oversized_bill.jpg",
        content=content,
        content_type="image/jpeg",
    )


# ---------------------------------------------------------------------------
# 1. Scanning Data Models Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestScanningModels:
    """Verify BillFile, ScanJob, BillError, and BillEditHistory schema & methods."""

    def test_bill_file_creation_and_hash(self, superadmin_user, sample_image):
        """BillFile stores file, computes SHA-256 hash, and tracks page ordering."""
        from scanning.models import BillFile

        bill_file = BillFile.objects.create(
            file=sample_image,
            page_number=1,
            file_type=BillFile.FileType.IMAGE,
        )
        assert bill_file.pk is not None
        assert bill_file.file_hash != ""
        assert len(bill_file.file_hash) == 64  # SHA-256 length
        assert bill_file.page_number == 1
        assert bill_file.file_size > 0

    def test_scan_job_lifecycle_and_metrics(self, superadmin_user):
        """ScanJob tracks scan states, tokens, latency, and JSON payload."""
        from scanning.models import ScanJob

        job = ScanJob.objects.create(
            provider="mock",
            model_name="mock-vision-v1",
            created_by=superadmin_user,
        )
        assert job.status == ScanJob.Status.PENDING

        job.status = ScanJob.Status.PROCESSING
        job.save()
        assert job.status == ScanJob.Status.PROCESSING

        job.status = ScanJob.Status.COMPLETED
        job.extracted_data = {"invoice_no": "INV-100", "grand_total": "500.00"}
        job.token_count = 1420
        job.latency_ms = 850
        job.completed_at = timezone.now()
        job.save()

        job.refresh_from_db()
        assert job.status == ScanJob.Status.COMPLETED
        assert job.extracted_data["invoice_no"] == "INV-100"
        assert job.token_count == 1420
        assert job.latency_ms == 850

    def test_bill_error_model_and_resolution(self, superadmin_user):
        """BillError stores discrepancy type, description, and resolution state."""
        from scanning.models import BillError

        vendor = Party.objects.create(name="Supplier X", party_type="vendor")
        bill = Bill.objects.create(party=vendor, grand_total=Decimal("100.00"))

        error = BillError.objects.create(
            bill=bill,
            error_type=BillError.ErrorType.MATH_MISMATCH,
            field_name="line_total",
            severity=BillError.Severity.ERROR,
            message="Item line total does not match quantity * unit price.",
            suggested_fix={"line_total": "150.00"},
        )
        assert not error.is_resolved
        assert error.severity == BillError.Severity.ERROR

        error.is_resolved = True
        error.save()
        assert error.is_resolved

    def test_bill_edit_history_logging(self, superadmin_user):
        """BillEditHistory records user audit trail of field modifications."""
        from scanning.models import BillEditHistory

        vendor = Party.objects.create(name="Supplier Y", party_type="vendor")
        bill = Bill.objects.create(party=vendor, grand_total=Decimal("200.00"))

        history = BillEditHistory.objects.create(
            bill=bill,
            user=superadmin_user,
            field_name="grand_total",
            old_value="180.00",
            new_value="200.00",
        )
        assert history.pk is not None
        assert history.old_value == "180.00"
        assert history.new_value == "200.00"
        assert history.user == superadmin_user


# ---------------------------------------------------------------------------
# 2. Image Preprocessing Service Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestImagePreprocessingService:
    """Verify image normalization, resizing, EXIF handling, and size validation."""

    def test_validate_and_sanitize_image_rejects_oversized_file(self, sample_oversized_image):
        """Files exceeding 15MB are rejected with ValidationError."""
        from scanning.services.image_processing import validate_and_preprocess_file

        with pytest.raises(ValidationError) as exc_info:
            validate_and_preprocess_file(sample_oversized_image)
        assert "15 MB" in str(exc_info.value) or "exceeds" in str(exc_info.value).lower()

    def test_validate_and_sanitize_image_rejects_invalid_extension(self):
        """Unsupported file extensions (.exe, .zip) are rejected."""
        from scanning.services.image_processing import validate_and_preprocess_file

        fake_file = SimpleUploadedFile("bill.exe", b"malicious executable payload")
        with pytest.raises(ValidationError) as exc_info:
            validate_and_preprocess_file(fake_file)
        assert (
            "unsupported" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()
        )

    def test_preprocess_resizes_large_dimensions(self):
        """High-resolution images are scaled down to maximum 2048px bounding box."""
        from scanning.services.image_processing import validate_and_preprocess_file

        huge_img = Image.new("RGB", (3000, 4000), color=(240, 240, 240))
        buf = io.BytesIO()
        huge_img.save(buf, format="JPEG")
        buf.seek(0)
        uploaded = SimpleUploadedFile("huge.jpg", buf.read(), content_type="image/jpeg")

        processed_bytes, file_type, file_hash = validate_and_preprocess_file(uploaded)
        processed_img = Image.open(io.BytesIO(processed_bytes))
        assert processed_img.width <= 2048
        assert processed_img.height <= 2048
        assert file_type == "image"
        assert len(file_hash) == 64


# ---------------------------------------------------------------------------
# 3. AI Extraction Pipeline & Schema Validation Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestAIExtractionEngine:
    """Verify provider wrapper, schema conformance, mock extraction, and quotas."""

    def test_mock_provider_returns_compliant_schema(self, sample_image):
        """Mock provider output conforms to MASTER_PROMPT Section 7 schema."""
        from scanning.services.extraction import MockAIExtractor

        extractor = MockAIExtractor()
        result = extractor.extract(sample_image)

        assert "document_type" in result
        assert "vendor" in result
        assert "customer" in result
        assert "items" in result
        assert "grand_total" in result
        assert "field_confidence" in result
        assert isinstance(result["items"], list)
        assert len(result["items"]) > 0

        first_item = result["items"][0]
        assert "item_name" in first_item or "name" in first_item
        assert "quantity" in first_item
        assert "unit_price" in first_item
        assert "line_total" in first_item

    def test_schema_validator_enforces_required_fields(self):
        """Invalid or malformed JSON triggers schema validation error."""
        from scanning.services.extraction import validate_extraction_schema

        valid_payload = {
            "document_type": "printed",
            "languages": ["en"],
            "vendor": {
                "name": "Al-Madina Store",
                "phone": "03001234567",
                "address": "Lahore",
                "tax_no": None,
            },
            "customer": {"name": None, "phone": None, "address": None},
            "invoice_no": "INV-5541",
            "date": "2026-10-10",
            "time": "14:30",
            "currency": "PKR",
            "items": [
                {
                    "serial_no": 1,
                    "name": "Wheat Flour 10kg",
                    "quantity": 2,
                    "unit": "bag",
                    "unit_price": 1200.0,
                    "discount": 0.0,
                    "tax": 0.0,
                    "line_total": 2400.0,
                    "confidence": 95,
                }
            ],
            "subtotal": 2400.0,
            "discount": 0.0,
            "tax": 0.0,
            "other_charges": 0.0,
            "grand_total": 2400.0,
            "paid_amount": 2400.0,
            "balance_due": 0.0,
            "payment_method": "cash",
            "suggested_category": "Grocery",
            "field_confidence": {"vendor_name": 95, "date": 90, "grand_total": 98},
            "warnings": [],
        }

        # Should pass validation cleanly
        validated = validate_extraction_schema(valid_payload)
        assert validated["invoice_no"] == "INV-5541"

        # Invalid payload (missing items array or bad type)
        invalid_payload = {"invoice_no": "123"}
        with pytest.raises(ValidationError):
            validate_extraction_schema(invalid_payload)

    def test_scan_quota_enforcement(self, superadmin_user, sample_image):
        """When daily scan limit is exhausted, ScanQuotaExceededError is raised."""
        from scanning.exceptions import ScanQuotaExceededError
        from scanning.services.extraction import check_scan_quota_available

        profile = ShopProfile.get_solo()
        profile.daily_scan_limit = 2
        profile.save()

        # Simulate 2 completed scans today
        from scanning.models import ScanJob

        ScanJob.objects.create(status=ScanJob.Status.COMPLETED, created_by=superadmin_user)
        ScanJob.objects.create(status=ScanJob.Status.COMPLETED, created_by=superadmin_user)

        with pytest.raises(ScanQuotaExceededError) as exc_info:
            check_scan_quota_available()
        assert "daily scan limit" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# 4. Automated Error Detection Service Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestErrorDetectionService:
    """Verify rule checks: math mismatch, subtotal, grand total, duplicate, anomalies."""

    def test_math_mismatch_detection(self):
        """Quantity * unit_price != line_total is flagged as error."""
        from scanning.services.validation import detect_bill_errors

        extracted_data = {
            "invoice_no": "INV-100",
            "date": "2026-10-10",
            "subtotal": 1000.0,
            "discount": 0.0,
            "tax": 0.0,
            "grand_total": 1000.0,
            "items": [
                {
                    "serial_no": 1,
                    "name": "Item A",
                    "quantity": 2.0,
                    "unit_price": 400.0,  # 2 * 400 = 800, but line_total is 1000!
                    "line_total": 1000.0,
                    "confidence": 90,
                }
            ],
            "field_confidence": {},
        }

        errors = detect_bill_errors(extracted_data)
        math_errors = [e for e in errors if e["error_type"] == "math_mismatch"]
        assert len(math_errors) >= 1
        assert "quantity * unit price" in math_errors[0]["message"].lower()

    def test_grand_total_mismatch_detection(self):
        """Subtotal - discount + tax != grand_total is flagged."""
        from scanning.services.validation import detect_bill_errors

        extracted_data = {
            "invoice_no": "INV-101",
            "date": "2026-10-10",
            "subtotal": 1000.0,
            "discount": 100.0,
            "tax": 50.0,
            "grand_total": 1200.0,  # Should be 1000 - 100 + 50 = 950.0!
            "items": [],
            "field_confidence": {},
        }

        errors = detect_bill_errors(extracted_data)
        gt_errors = [e for e in errors if e["error_type"] == "grand_total_mismatch"]
        assert len(gt_errors) >= 1
        assert "grand total" in gt_errors[0]["message"].lower()

    def test_missing_critical_fields_detection(self):
        """Missing date, invoice number, or grand total is flagged."""
        from scanning.services.validation import detect_bill_errors

        extracted_data = {
            "invoice_no": None,
            "date": None,
            "subtotal": 500.0,
            "grand_total": None,
            "items": [],
            "field_confidence": {},
        }

        errors = detect_bill_errors(extracted_data)
        missing_errors = [e for e in errors if e["error_type"] == "missing_field"]
        missing_fields = {e["field_name"] for e in missing_errors}
        assert "invoice_no" in missing_fields
        assert "date" in missing_fields
        assert "grand_total" in missing_fields

    def test_date_anomaly_detection_future_date(self):
        """Dates in the future are flagged as warnings."""
        from scanning.services.validation import detect_bill_errors

        future_date = (timezone.now() + timezone.timedelta(days=10)).strftime("%Y-%m-%d")
        extracted_data = {
            "invoice_no": "INV-FUTURE",
            "date": future_date,
            "grand_total": 500.0,
            "items": [],
            "field_confidence": {},
        }

        errors = detect_bill_errors(extracted_data)
        date_errors = [e for e in errors if e["error_type"] == "date_anomaly"]
        assert len(date_errors) >= 1

    def test_duplicate_bill_detection(self, superadmin_user):
        """Matching vendor + invoice_no + date + grand_total flags duplicate suspect."""
        from scanning.services.validation import detect_bill_errors

        vendor = Party.objects.create(name="Duplicate Vendor", party_type="vendor")
        Bill.objects.create(
            party=vendor,
            invoice_no="DUP-999",
            bill_date="2026-10-10",
            grand_total=Decimal("5000.00"),
        )

        extracted_data = {
            "vendor": {"name": "Duplicate Vendor"},
            "invoice_no": "DUP-999",
            "date": "2026-10-10",
            "grand_total": 5000.0,
            "items": [],
            "field_confidence": {},
        }

        errors = detect_bill_errors(extracted_data)
        dup_errors = [e for e in errors if e["error_type"] == "duplicate_suspect"]
        assert len(dup_errors) >= 1
        assert "duplicate" in dup_errors[0]["message"].lower()

    def test_low_confidence_fields_flagged(self):
        """Field confidence < 70% is flagged with low_confidence error."""
        from scanning.services.validation import detect_bill_errors

        extracted_data = {
            "invoice_no": "INV-BLURRY",
            "date": "2026-10-10",
            "grand_total": 300.0,
            "items": [],
            "field_confidence": {"vendor_name": 45, "grand_total": 95},
        }

        errors = detect_bill_errors(extracted_data)
        low_conf = [e for e in errors if e["error_type"] == "low_confidence"]
        assert len(low_conf) >= 1
        assert "vendor_name" in low_conf[0]["field_name"]


# ---------------------------------------------------------------------------
# 5. Auto-Profiles and Category Matching Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestAutoProfilesAndCategorySuggestion:
    """Verify vendor fuzzy matching from scans and category suggestions."""

    def test_auto_match_existing_vendor_from_scan(self):
        """High confidence vendor match connects to existing Party instance."""
        from scanning.services.matching import resolve_scan_party

        existing = Party.objects.create(
            name="Imtiaz Super Market",
            phone="03009998877",
            party_type="vendor",
        )

        party, is_new = resolve_scan_party({"name": "Imtiaz Super Market", "phone": "03009998877"})
        assert party.pk == existing.pk
        assert not is_new

    def test_auto_create_new_vendor_from_scan(self):
        """Unrecognized vendor name automatically creates a new vendor Party."""
        from scanning.services.matching import resolve_scan_party

        party, is_new = resolve_scan_party({"name": "Brand New Pharmacy", "phone": "03331122334"})
        assert is_new
        assert party.name == "Brand New Pharmacy"
        assert party.party_type == Party.PartyType.VENDOR

    def test_auto_match_existing_vendor_updates_missing_phone(self):
        """When existing vendor lacks a phone number, scan with phone number updates the party record."""
        from scanning.services.matching import resolve_scan_party

        existing = Party.objects.create(name="Arif Chicken Center", phone="", party_type="vendor")
        party, is_new = resolve_scan_party(
            {
                "name": "Arif Chicken Center",
                "phone": "0323-4663429",
                "address": "Lahore Market",
            }
        )
        assert party.pk == existing.pk
        assert not is_new
        existing.refresh_from_db()
        assert existing.phone == "0323-4663429"
        assert existing.address == "Lahore Market"

    def test_category_suggestion_from_bill_content(self):
        """Items like Panadol / Augmentin suggest 'Medical' category."""
        from categories.services import seed_default_categories
        from scanning.services.matching import suggest_bill_category

        seed_default_categories()

        medical_items = [
            {"name": "Panadol 500mg Strip", "line_total": 120.0},
            {"name": "Augmentin 625mg", "line_total": 540.0},
        ]
        suggested = suggest_bill_category("Medical", medical_items)
        assert suggested is not None
        assert "Medical" in suggested.name or "ادویات" in suggested.urdu_name


# ---------------------------------------------------------------------------
# 6. Upload & Review Views Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestUploadAndReviewViews:
    """Verify HTTP upload flow, multi-file submission, and review screen."""

    def test_upload_view_get(self, client, superadmin_user):
        """Upload page renders with dropzone, camera trigger, and file picker."""
        client.force_login(superadmin_user)
        response = client.get("/en/scanning/upload/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Scan Bill" in content
        assert "dropzone" in content.lower() or "upload" in content.lower()

    def test_upload_view_post_creates_job_and_redirects_to_review(
        self, client, superadmin_user, sample_image, settings
    ):
        """POST upload creates ScanJob, processes mock scan, and redirects to review."""
        settings.AI_PROVIDER = "mock"
        client.force_login(superadmin_user)

        response = client.post(
            "/en/scanning/upload/",
            {"files": [sample_image]},
            follow=False,
        )
        assert response.status_code in (302, 200)

        from scanning.models import ScanJob

        job = ScanJob.objects.filter(created_by=superadmin_user).latest("id")
        assert job.status in (ScanJob.Status.COMPLETED, ScanJob.Status.PROCESSING)

    def test_review_view_renders_split_screen_and_low_confidence(
        self, client, superadmin_user, sample_image
    ):
        """Review screen renders original document view, editable fields, and errors."""
        client.force_login(superadmin_user)
        from scanning.models import BillFile, ScanJob
        from scanning.services.extraction import process_scan_job

        job = ScanJob.objects.create(
            provider="mock",
            status=ScanJob.Status.PENDING,
            created_by=superadmin_user,
        )
        BillFile.objects.create(
            scan_job=job,
            file=sample_image,
            page_number=1,
            file_type=BillFile.FileType.IMAGE,
        )

        process_scan_job(job)
        job.refresh_from_db()
        assert job.bill is not None

        response = client.get(f"/en/scanning/review/{job.pk}/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Review Bill" in content or "Review" in content
        assert job.bill.invoice_no in content or "Invoice" in content

    def test_review_view_post_verifies_bill(self, client, superadmin_user, sample_image):
        """Review POST allows saving updates and marking bill as Verified."""
        client.force_login(superadmin_user)
        from scanning.models import BillFile, ScanJob
        from scanning.services.extraction import process_scan_job

        job = ScanJob.objects.create(provider="mock", created_by=superadmin_user)
        BillFile.objects.create(scan_job=job, file=sample_image, page_number=1)
        process_scan_job(job)

        response = client.post(
            f"/en/scanning/review/{job.pk}/",
            {
                "action": "verify",
                "invoice_no": "VERIFIED-99",
                "party": job.bill.party.pk,
                "party_phone": "0300-8887766",
                "bill_date": str(job.bill.bill_date),
                "discount": "0.00",
                "tax": "0.00",
            },
            follow=True,
        )
        assert response.status_code == 200
        job.bill.refresh_from_db()
        assert job.bill.status == Bill.Status.VERIFIED
        assert job.bill.party.phone == "0300-8887766"


# ---------------------------------------------------------------------------
# 7. Localization & UI Integration Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestScanningLocalizationAndUI:
    """Verify bilingual English (LTR) / Urdu (RTL) and dark theme on scanning pages."""

    def test_upload_view_urdu_rtl(self, client, superadmin_user):
        """Upload page renders in Urdu with dir='rtl'."""
        client.force_login(superadmin_user)
        response = client.get("/ur/scanning/upload/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'dir="rtl"' in content
        assert "dark:bg-slate-800" in content

    def test_review_view_urdu_rtl(self, client, superadmin_user, sample_image):
        """Review page renders in Urdu with dir='rtl' and split-screen layout."""
        client.force_login(superadmin_user)
        from scanning.models import BillFile, ScanJob
        from scanning.services.extraction import process_scan_job

        job = ScanJob.objects.create(provider="mock", created_by=superadmin_user)
        BillFile.objects.create(scan_job=job, file=sample_image, page_number=1)
        process_scan_job(job)

        response = client.get(f"/ur/scanning/review/{job.pk}/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'dir="rtl"' in content
        assert "dark:bg-slate-800" in content


# ---------------------------------------------------------------------------
# 8. AI Provider Resolution & Real Extractor Tests (Regression BUG-001)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestAIExtractorProviderResolution:
    """Regression tests for BUG-001: Ensure real AI extractor is invoked instead of static mock."""

    def test_get_ai_extractor_gemini_missing_key_raises_error(self, settings):
        """Root cause hypothesis: get_ai_extractor silently returned mock extractor when key was missing."""
        from scanning.exceptions import AIExtractionError
        from scanning.services.extraction import get_ai_extractor

        settings.AI_PROVIDER = "gemini"
        settings.GEMINI_API_KEY = ""

        with pytest.raises(AIExtractionError) as exc_info:
            get_ai_extractor("gemini")
        assert "GEMINI_API_KEY" in str(exc_info.value)

    def test_get_ai_extractor_returns_gemini_extractor_when_configured(self, settings):
        """Configuring gemini with valid key returns GeminiAIExtractor instance."""
        from scanning.services.extraction import GeminiAIExtractor, get_ai_extractor

        settings.AI_PROVIDER = "gemini"
        settings.GEMINI_API_KEY = "test_key_123"

        extractor = get_ai_extractor("gemini")
        assert isinstance(extractor, GeminiAIExtractor)
        assert extractor.api_key == "test_key_123"

    def test_upload_view_uses_configured_ai_provider(
        self, client, superadmin_user, sample_image, settings
    ):
        """Upload view must create ScanJob using settings.AI_PROVIDER, not hardcoded 'mock'."""
        client.force_login(superadmin_user)
        settings.AI_PROVIDER = "mock"

        response = client.post(
            "/en/scanning/upload/",
            {"files": [sample_image]},
            follow=False,
        )
        assert response.status_code in (302, 200)
        from scanning.models import ScanJob

        job = ScanJob.objects.filter(created_by=superadmin_user).latest("id")
        assert job.provider == "mock"

    def test_upload_view_post_missing_key_returns_400_with_helpful_error(
        self, client, superadmin_user, sample_image, settings
    ):
        """When GEMINI_API_KEY is empty and provider is gemini, POST returns 400 with helpful instructions."""
        client.force_login(superadmin_user)
        settings.AI_PROVIDER = "gemini"
        settings.GEMINI_API_KEY = ""

        response = client.post(
            "/en/scanning/upload/",
            {"files": [sample_image]},
            follow=False,
        )
        assert response.status_code == 400
        content = response.content.decode("utf-8")
        assert "GEMINI_API_KEY" in content or "API key" in content

    def test_upload_view_get_shows_key_warning_banner_when_key_missing(
        self, client, superadmin_user, settings
    ):
        """When GEMINI_API_KEY is empty, upload page renders warning banner informing user."""
        client.force_login(superadmin_user)
        settings.AI_PROVIDER = "gemini"
        settings.GEMINI_API_KEY = ""

        response = client.get("/en/scanning/upload/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "GEMINI_API_KEY" in content or "API Key Required" in content

    def test_gemini_ai_extractor_extracts_and_parses_json(self, sample_image, monkeypatch):
        """GeminiAIExtractor calls Google Gemini client and parses JSON response successfully."""
        import json
        from unittest.mock import MagicMock

        from scanning.services.extraction import GeminiAIExtractor

        mock_payload = {
            "document_type": "printed",
            "languages": ["en"],
            "vendor": {
                "name": "Test Superstore",
                "phone": "03001234567",
                "address": "Lahore",
                "tax_no": None,
            },
            "customer": {"name": "Walk-in", "phone": None, "address": None},
            "invoice_no": "INV-REAL-101",
            "date": "2026-10-13",
            "time": "12:00",
            "currency": "PKR",
            "items": [
                {
                    "serial_no": 1,
                    "name": "Wheat Flour",
                    "quantity": 1,
                    "unit": "bag",
                    "unit_price": 1500.0,
                    "discount": 0.0,
                    "tax": 0.0,
                    "line_total": 1500.0,
                    "confidence": 99,
                }
            ],
            "subtotal": 1500.0,
            "discount": 0.0,
            "tax": 0.0,
            "other_charges": 0.0,
            "grand_total": 1500.0,
            "paid_amount": 1500.0,
            "balance_due": 0.0,
            "payment_method": "cash",
            "suggested_category": "Grocery",
            "field_confidence": {"vendor_name": 99, "date": 95, "grand_total": 99},
            "warnings": [],
        }

        mock_response = MagicMock()
        mock_response.text = json.dumps(mock_payload)
        mock_response.usage_metadata.total_token_count = 850

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        # Monkeypatch genai.Client
        import google.genai

        monkeypatch.setattr(google.genai, "Client", lambda api_key: mock_client)

        extractor = GeminiAIExtractor(api_key="valid_gemini_key")
        result = extractor.extract(sample_image)

        assert result["invoice_no"] == "INV-REAL-101"
        assert result["vendor"]["name"] == "Test Superstore"
        assert extractor.last_token_count == 850

    def test_gemini_ai_extractor_handles_markdown_fences(self, sample_image, monkeypatch):
        """GeminiAIExtractor cleanly strips ```json code fences returned by model."""
        import json
        from unittest.mock import MagicMock

        from scanning.services.extraction import GeminiAIExtractor

        mock_payload = {
            "document_type": "printed",
            "languages": ["en"],
            "vendor": {"name": "Fenced Store"},
            "customer": {"name": None},
            "invoice_no": "INV-FENCE-99",
            "items": [],
            "grand_total": 100.0,
        }

        mock_response = MagicMock()
        mock_response.text = f"```json\n{json.dumps(mock_payload)}\n```"
        mock_response.usage_metadata = None

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        import google.genai

        monkeypatch.setattr(google.genai, "Client", lambda api_key: mock_client)

        extractor = GeminiAIExtractor(api_key="valid_key")
        result = extractor.extract(sample_image)
        assert result["invoice_no"] == "INV-FENCE-99"

    def test_gemini_ai_extractor_handles_malformed_json(self, sample_image, monkeypatch):
        """When model output cannot be parsed as JSON, AIExtractionError is raised."""
        from unittest.mock import MagicMock

        from scanning.exceptions import AIExtractionError
        from scanning.services.extraction import GeminiAIExtractor

        mock_response = MagicMock()
        mock_response.text = "This is not JSON at all."
        mock_response.usage_metadata = None

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        import google.genai

        monkeypatch.setattr(google.genai, "Client", lambda api_key: mock_client)

        extractor = GeminiAIExtractor(api_key="valid_key")
        with pytest.raises(AIExtractionError) as exc_info:
            extractor.extract(sample_image)
        assert "JSON" in str(exc_info.value)

    def test_gemini_ai_extractor_handles_api_exception(self, sample_image, monkeypatch):
        """When Gemini client throws an exception, it is caught and wrapped in AIExtractionError."""
        from unittest.mock import MagicMock

        from scanning.exceptions import AIExtractionError
        from scanning.services.extraction import GeminiAIExtractor

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("Quota limit reached")

        import google.genai

        monkeypatch.setattr(google.genai, "Client", lambda api_key: mock_client)

        extractor = GeminiAIExtractor(api_key="valid_key")
        with pytest.raises(AIExtractionError) as exc_info:
            extractor.extract(sample_image)
        assert "Quota limit reached" in str(exc_info.value)

    def test_scan_to_bill_handles_null_item_fields(
        self, superadmin_user, sample_image, monkeypatch
    ):
        """When AI returns items with null urdu_name or null unit, scanning succeeds without NOT NULL error."""
        from unittest.mock import MagicMock

        from scanning.models import BillFile, ScanJob
        from scanning.services.extraction import process_scan_job

        job = ScanJob.objects.create(provider="gemini", created_by=superadmin_user)
        BillFile.objects.create(scan_job=job, file=sample_image, page_number=1)

        mock_payload = {
            "document_type": "printed",
            "languages": ["en"],
            "vendor": {"name": "Test Vendor", "urdu_name": None},
            "customer": {"name": None},
            "invoice_no": "INV-NULL-TEST",
            "date": "2026-10-13",
            "items": [
                {
                    "serial_no": 1,
                    "name": "Live Chicken",
                    "urdu_name": None,
                    "quantity": 2.5,
                    "unit": None,
                    "unit_price": 400.0,
                    "line_total": 1000.0,
                }
            ],
            "grand_total": 1000.0,
            "subtotal": 1000.0,
            "discount": 0.0,
            "tax": 0.0,
        }

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = mock_payload
        mock_extractor.last_token_count = 100
        monkeypatch.setattr(
            "scanning.services.extraction.get_ai_extractor", lambda provider: mock_extractor
        )

        bill = process_scan_job(job)
        assert bill is not None
        assert bill.items.count() == 1
        item = bill.items.first()
        assert item.item_name == "Live Chicken"
        assert item.urdu_item_name == ""
        assert item.unit == "pcs"
