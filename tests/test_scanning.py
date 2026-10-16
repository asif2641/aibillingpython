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
from PIL import Image, ImageDraw

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
    """Create a dummy in-memory JPEG bill image with readable content."""
    img = Image.new("RGB", (800, 1000), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    for y in range(80, 920, 50):
        draw.text((60, y), f"Sample Bill Line Item #{y} Qty 2 Price 450 Total 900", fill=(0, 0, 0))
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

        huge_img = Image.new("RGB", (3000, 4000), color=(255, 255, 255))
        draw = ImageDraw.Draw(huge_img)
        for y in range(200, 3800, 200):
            draw.text(
                (200, y), f"Huge Bill Line Item #{y} Qty 1 Price 500 Total 500", fill=(0, 0, 0)
            )
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


class TestImageQualityAssessment:
    """Tests for pre-AI document quality checks: blurry, too dark, blank page, and under-100px."""

    def _create_image_file(self, img: Image.Image, name: str = "doc.jpg") -> SimpleUploadedFile:
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        return SimpleUploadedFile(name=name, content=buf.read(), content_type="image/jpeg")

    def test_valid_sharp_bill_passes_quality_assessment(self):
        """A normal, sharp, well-lit bill passes quality assessment cleanly."""
        from scanning.services.image_processing import (
            assess_image_quality,
            validate_and_preprocess_file,
        )

        img = Image.new("RGB", (800, 1000), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        for y in range(80, 920, 50):
            draw.text(
                (60, y), f"Al-Madina Store Item #{y} Qty 2 Rate 450 Total 900", fill=(0, 0, 0)
            )

        report = assess_image_quality(img)
        assert report.is_valid is True
        assert report.issue_code is None
        assert report.error_message == ""
        assert report.metrics["width"] == 800
        assert report.metrics["height"] == 1000

        uploaded = self._create_image_file(img)
        processed_bytes, file_type, _ = validate_and_preprocess_file(uploaded)
        assert file_type == "image"
        assert len(processed_bytes) > 0

    def test_too_small_image_rejected(self):
        """Images under 100px in either dimension are rejected with too_small error."""
        from scanning.services.image_processing import (
            assess_image_quality,
            validate_and_preprocess_file,
        )

        small_img = Image.new("RGB", (80, 120), color=(255, 255, 255))
        draw = ImageDraw.Draw(small_img)
        draw.text((10, 10), "Tiny", fill=(0, 0, 0))

        report = assess_image_quality(small_img)
        assert report.is_valid is False
        assert report.issue_code == "too_small"
        assert "100px" in report.error_message or "small" in report.error_message.lower()

        uploaded = self._create_image_file(small_img)
        with pytest.raises(ValidationError) as exc:
            validate_and_preprocess_file(uploaded)
        assert "100px" in str(exc.value) or "small" in str(exc.value).lower()

    def test_too_dark_low_light_image_rejected(self):
        """Images with mean luminance below 35 are rejected as too dark."""
        from scanning.services.image_processing import (
            assess_image_quality,
            validate_and_preprocess_file,
        )

        dark_img = Image.new("RGB", (800, 1000), color=(18, 18, 18))
        draw = ImageDraw.Draw(dark_img)
        draw.text((60, 100), "Dim unreadable text in darkness", fill=(30, 30, 30))

        report = assess_image_quality(dark_img)
        assert report.is_valid is False
        assert report.issue_code == "too_dark"
        assert "dark" in report.error_message.lower() or "lighting" in report.error_message.lower()

        uploaded = self._create_image_file(dark_img)
        with pytest.raises(ValidationError) as exc:
            validate_and_preprocess_file(uploaded)
        assert "dark" in str(exc.value).lower() or "lighting" in str(exc.value).lower()

    def test_blank_page_image_rejected(self):
        """Images with uniform blank background and zero/low contrast are rejected as blank_page."""
        from scanning.services.image_processing import (
            assess_image_quality,
            validate_and_preprocess_file,
        )

        blank_img = Image.new("RGB", (800, 1000), color=(250, 250, 250))

        report = assess_image_quality(blank_img)
        assert report.is_valid is False
        assert report.issue_code == "blank_page"
        assert "blank" in report.error_message.lower()

        uploaded = self._create_image_file(blank_img)
        with pytest.raises(ValidationError) as exc:
            validate_and_preprocess_file(uploaded)
        assert "blank" in str(exc.value).lower()

    def test_blurry_image_rejected(self):
        """Images blurred by camera defocus/shake are rejected with blurry error."""
        from PIL import ImageFilter

        from scanning.services.image_processing import (
            assess_image_quality,
            validate_and_preprocess_file,
        )

        sharp_img = Image.new("RGB", (800, 1000), color=(255, 255, 255))
        draw = ImageDraw.Draw(sharp_img)
        for y in range(80, 920, 50):
            draw.text(
                (60, y), f"Al-Madina Store Item #{y} Qty 2 Rate 450 Total 900", fill=(0, 0, 0)
            )

        blurry_img = sharp_img.filter(ImageFilter.GaussianBlur(radius=5))

        report = assess_image_quality(blurry_img)
        assert report.is_valid is False
        assert report.issue_code == "blurry"
        assert "blurry" in report.error_message.lower()

        uploaded = self._create_image_file(blurry_img)
        with pytest.raises(ValidationError) as exc:
            validate_and_preprocess_file(uploaded)
        assert "blurry" in str(exc.value).lower()

    def test_pdf_document_ignores_image_blur_check(self):
        """PDF documents pass through without image blur inspection."""
        from scanning.services.image_processing import validate_and_preprocess_file

        pdf_payload = b"%PDF-1.4 sample pdf content for multi-page invoices"
        uploaded_pdf = SimpleUploadedFile(
            "invoice.pdf", pdf_payload, content_type="application/pdf"
        )

        processed_bytes, file_type, file_hash = validate_and_preprocess_file(uploaded_pdf)
        assert file_type == "pdf"
        assert processed_bytes == pdf_payload
        assert len(file_hash) == 64

    def test_urdu_quality_error_messages(self):
        """When active language is Urdu, quality messages return friendly Urdu text."""
        from django.utils import translation

        from scanning.services.image_processing import get_quality_error_message

        with translation.override("ur"):
            assert "100 پکسل" in get_quality_error_message("too_small")
            assert "اندھیرا" in get_quality_error_message("too_dark")
            assert "خالی صفحہ" in get_quality_error_message("blank_page")
            assert "دھندلی" in get_quality_error_message("blurry")

    @pytest.mark.django_db
    def test_upload_view_rejects_blurry_image_before_ai_job(self, client, superadmin_user):
        """Upload view returns HTTP 400 and prevents ScanJob creation when image is blurry."""
        from django.urls import reverse
        from PIL import ImageFilter

        from scanning.models import ScanJob

        sharp_img = Image.new("RGB", (800, 1000), color=(255, 255, 255))
        draw = ImageDraw.Draw(sharp_img)
        for y in range(80, 920, 50):
            draw.text((60, y), f"Receipt Item #{y} Description 500", fill=(0, 0, 0))
        blurry_file = self._create_image_file(sharp_img.filter(ImageFilter.GaussianBlur(5)))

        client.force_login(superadmin_user)
        initial_job_count = ScanJob.objects.count()

        response = client.post(
            reverse("scanning:upload"),
            {"files": [blurry_file]},
            follow=True,
        )

        assert response.status_code == 400
        # No ScanJob created
        assert ScanJob.objects.count() == initial_job_count
        content = response.content.decode("utf-8")
        assert "blurry" in content.lower() or "دھندلی" in content


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

    def test_round_half_up_unit_price_does_not_trigger_math_mismatch(self):
        """When unit_price is 2-decimal rounded half-up (e.g. 130/6=21.666..->21.67), no math error is raised."""
        from scanning.services.validation import detect_bill_errors

        # 6 eggs @ 21.67 = 130.02 (diff 0.02 from line_total 130)
        extracted_data = {
            "invoice_no": "INV-100B",
            "date": "2026-10-10",
            "subtotal": 130.0,
            "discount": 0.0,
            "tax": 0.0,
            "grand_total": 130.0,
            "items": [
                {
                    "serial_no": 1,
                    "name": "Eggs",
                    "quantity": 6.0,
                    "unit_price": 21.67,  # 130 / 6 = 21.6666... rounded half-up to 21.67
                    "line_total": 130.0,
                    "confidence": 95,
                }
            ],
            "field_confidence": {},
        }

        errors = detect_bill_errors(extracted_data)
        math_errors = [e for e in errors if e["error_type"] == "math_mismatch"]
        assert len(math_errors) == 0

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

    def test_check_duplicate_view_returns_duplicate_data(
        self, client, superadmin_user, sample_image
    ):
        """check_duplicate endpoint returns duplicate info when matching file hash exists."""
        client.force_login(superadmin_user)
        from bills.models import Bill
        from parties.models import Party
        from scanning.models import BillFile, ScanJob

        party = Party.objects.create(name="Vendor A", party_type="vendor")
        sample_bill = Bill.objects.create(
            party=party,
            invoice_no="INV-DUP-TEST",
            bill_date="2026-10-13",
            grand_total=Decimal("500.00"),
        )

        job = ScanJob.objects.create(
            provider="mock", bill=sample_bill, status=ScanJob.Status.COMPLETED
        )
        bf = BillFile.objects.create(
            scan_job=job,
            bill=sample_bill,
            file=sample_image,
            page_number=1,
            file_hash="test_hash_abcdef1234567890",
        )

        # Non-matching hash
        resp = client.get("/en/scanning/check-duplicate/?hash=different_hash_123456789")
        assert resp.status_code == 200
        assert resp.json()["is_duplicate"] is False

        # Matching hash
        resp = client.get(f"/en/scanning/check-duplicate/?hash={bf.file_hash}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_duplicate"] is True
        assert data["bill_id"] == sample_bill.pk
        assert data["party_name"] == sample_bill.party.name

    def test_client_raw_file_hash_matches_preprocessed_file_duplicate_check(
        self, client, superadmin_user, sample_image
    ):
        """BUG-006: Verify that the raw client-side file hash matches the server's duplicate detection,
        preventing missed duplicate detection caused by Pillow JPEG recompression hash mismatch.
        """
        import hashlib

        from bills.models import Bill
        from parties.models import Party
        from scanning.models import BillFile, ScanJob
        from scanning.services.image_processing import validate_and_preprocess_file

        client.force_login(superadmin_user)

        # 1. Compute raw client SHA-256 (what browser crypto.subtle calculates)
        sample_image.seek(0)
        raw_bytes = sample_image.read()
        sample_image.seek(0)
        client_raw_hash = hashlib.sha256(raw_bytes).hexdigest()

        # 2. Server preprocesses and validates
        processed_bytes, file_type, file_hash = validate_and_preprocess_file(sample_image)
        # file_hash must equal client_raw_hash so the pre-scan duplicate check matches!
        assert file_hash == client_raw_hash

        # 3. Simulate existing scanned bill with this file
        party = Party.objects.create(name="Al-Madina Traders", party_type="vendor")
        existing_bill = Bill.objects.create(
            party=party,
            invoice_no="INV-1234",
            bill_date="2026-10-15",
            grand_total=Decimal("3500.00"),
        )
        job = ScanJob.objects.create(
            provider="mock", bill=existing_bill, status=ScanJob.Status.COMPLETED
        )
        BillFile.objects.create(
            scan_job=job,
            bill=existing_bill,
            file=sample_image,
            file_hash=file_hash,
            raw_hash=client_raw_hash,
        )

        # 4. Client sends its raw hash to check-duplicate endpoint
        resp = client.get(
            f"/en/scanning/check-duplicate/?hash={client_raw_hash}&name=test_bill.jpg&size={len(raw_bytes)}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_duplicate"] is True
        assert data["bill_id"] == existing_bill.pk
        assert data["invoice_no"] == "INV-1234"
        assert data["party_name"] == "Al-Madina Traders"
        assert data["grand_total"] == "3500.00"

    def test_upload_post_pre_scan_duplicate_gate_blocks_redundant_scan(
        self, client, superadmin_user, sample_image
    ):
        """BUG-006: Uploading a duplicate file via POST is caught before running AI/ScanJob,
        displaying an actionable duplicate warning with a link to the existing bill.
        """
        import hashlib

        from bills.models import Bill
        from parties.models import Party
        from scanning.models import BillFile, ScanJob

        client.force_login(superadmin_user)

        sample_image.seek(0)
        raw_bytes = sample_image.read()
        sample_image.seek(0)
        raw_hash = hashlib.sha256(raw_bytes).hexdigest()

        party = Party.objects.create(name="Apex Supplies", party_type="vendor")
        existing_bill = Bill.objects.create(
            party=party,
            invoice_no="INV-PRESCAN",
            bill_date="2026-10-15",
            grand_total=Decimal("2900.00"),
        )
        job = ScanJob.objects.create(
            provider="mock", bill=existing_bill, status=ScanJob.Status.COMPLETED
        )
        BillFile.objects.create(
            scan_job=job,
            bill=existing_bill,
            file=sample_image,
            file_hash=raw_hash,
            raw_hash=raw_hash,
        )

        initial_bill_count = Bill.objects.count()
        initial_job_count = ScanJob.objects.count()

        # Upload duplicate without force_rescan
        sample_image.seek(0)
        resp = client.post("/en/scanning/upload/", {"files": [sample_image]})
        assert resp.status_code == 200
        assert resp.context["duplicate_detected"] is True
        assert resp.context["duplicate_bill"].pk == existing_bill.pk
        assert "Duplicate Bill Detected" in resp.content.decode("utf-8")

        # Verify NO new bill or ScanJob was created (zero AI waste)
        assert Bill.objects.count() == initial_bill_count
        assert ScanJob.objects.count() == initial_job_count

        # Upload WITH force_rescan=1 allows user to intentionally create second copy
        sample_image.seek(0)
        resp_forced = client.post(
            "/en/scanning/upload/", {"files": [sample_image], "force_rescan": "1"}
        )
        assert resp_forced.status_code == 302
        assert Bill.objects.count() == initial_bill_count + 1

    def test_process_scan_job_fast_tracks_duplicate_document(
        self, superadmin_user, sample_image, monkeypatch
    ):
        """When an identical document hash exists with completed bill, process_scan_job fast-tracks without calling AI extractor."""
        from bills.models import Bill
        from parties.models import Party
        from scanning.models import BillError, BillFile, ScanJob
        from scanning.services.extraction import process_scan_job

        party = Party.objects.create(name="Vendor Fast Track", party_type="vendor")
        sample_bill = Bill.objects.create(
            party=party,
            invoice_no="INV-FAST",
            bill_date="2026-10-13",
            grand_total=Decimal("500.00"),
        )

        prev_job = ScanJob.objects.create(
            provider="mock",
            bill=sample_bill,
            status=ScanJob.Status.COMPLETED,
            extracted_data={
                "document_type": "printed",
                "vendor": {"name": sample_bill.party.name},
                "items": [
                    {"name": "Cached Item", "quantity": 1, "unit_price": 500, "line_total": 500}
                ],
                "grand_total": 500.0,
            },
        )
        test_hash = "unique_cached_file_hash_987654321"
        BillFile.objects.create(
            scan_job=prev_job,
            bill=sample_bill,
            file=sample_image,
            page_number=1,
            file_hash=test_hash,
        )

        new_job = ScanJob.objects.create(provider="gemini", created_by=superadmin_user)
        BillFile.objects.create(
            scan_job=new_job,
            file=sample_image,
            page_number=1,
            file_hash=test_hash,
        )

        # If it calls AI extractor, raise an error to prove it was skipped!
        def fail_if_called(*args, **kwargs):
            raise AssertionError("AI Extractor should NOT be called for duplicate documents!")

        monkeypatch.setattr("scanning.services.extraction.get_ai_extractor", fail_if_called)

        new_bill = process_scan_job(new_job)
        assert new_bill is not None
        assert new_bill.items.filter(item_name="Cached Item").exists()
        assert new_bill.errors.filter(error_type=BillError.ErrorType.DUPLICATE_SUSPECT).exists()

    def test_deleted_bill_not_flagged_as_duplicate(self, client, superadmin_user, sample_image):
        """When an earlier bill was deleted, re-uploading the same document does NOT flag duplicate suspect."""
        from bills.models import Bill
        from parties.models import Party
        from scanning.models import BillError, BillFile, ScanJob
        from scanning.services.extraction import process_scan_job

        vendor = Party.objects.create(name="Deleted Vendor", party_type="vendor")
        old_bill = Bill.all_objects.create(
            party=vendor,
            bill_date="2026-10-13",
            grand_total=Decimal("600.00"),
            is_deleted=True,  # DELETED bill!
        )

        old_job = ScanJob.objects.create(
            provider="mock",
            bill=old_bill,
            status=ScanJob.Status.COMPLETED,
            extracted_data={
                "document_type": "printed",
                "vendor": {"name": "Deleted Vendor"},
                "items": [
                    {
                        "name": "Item Once Deleted",
                        "quantity": 1,
                        "unit_price": 600,
                        "line_total": 600,
                    }
                ],
                "grand_total": 600.0,
            },
        )
        test_hash = "hash_of_deleted_document_12345"
        BillFile.objects.create(
            scan_job=old_job,
            bill=old_bill,
            file=sample_image,
            page_number=1,
            file_hash=test_hash,
        )

        # 1. Check duplicate endpoint returns False
        client.force_login(superadmin_user)
        response = client.get(f"/en/scanning/check-duplicate/?hash={test_hash}")
        assert response.status_code == 200
        assert response.json()["is_duplicate"] is False

        # 2. Process new scan job: data is reused from cache for speed, but NO duplicate warning is raised!
        new_job = ScanJob.objects.create(provider="mock", created_by=superadmin_user)
        BillFile.objects.create(
            scan_job=new_job,
            file=sample_image,
            page_number=1,
            file_hash=test_hash,
        )

        new_bill = process_scan_job(new_job)
        assert new_bill is not None
        assert not new_bill.errors.filter(error_type=BillError.ErrorType.DUPLICATE_SUSPECT).exists()

    def test_newly_scanned_bill_not_flagged_as_duplicate_of_itself(
        self, superadmin_user, sample_image
    ):
        """A freshly uploaded bill with an invoice_no and grand_total must NOT flag duplicate_suspect against itself."""
        from scanning.models import BillError, BillFile, ScanJob
        from scanning.services.extraction import process_scan_job

        job = ScanJob.objects.create(
            provider="mock",
            created_by=superadmin_user,
            extracted_data={
                "document_type": "printed",
                "vendor": {"name": "First Time Vendor"},
                "invoice_no": "UNIQUE-INV-101",
                "date": "2026-10-14",
                "subtotal": 1000.0,
                "grand_total": 1000.0,
                "items": [
                    {
                        "name": "Widget A",
                        "quantity": 1,
                        "unit_price": 1000.0,
                        "line_total": 1000.0,
                    }
                ],
            },
        )
        BillFile.objects.create(
            scan_job=job,
            file=sample_image,
            page_number=1,
            file_hash="unique_hash_101",
        )

        bill = process_scan_job(job)
        assert bill is not None
        dup_errors = bill.errors.filter(error_type=BillError.ErrorType.DUPLICATE_SUSPECT)
        assert (
            not dup_errors.exists()
        ), f"Bill was falsely flagged as duplicate of itself: {[e.message for e in dup_errors]}"

    def test_customer_profile_auto_created_from_scan(
        self, monkeypatch, superadmin_user, sample_image
    ):
        """When an extracted bill contains customer details, a Customer Party profile is auto-created."""
        from parties.models import Party
        from scanning.models import BillFile, ScanJob
        from scanning.services.extraction import process_scan_job

        custom_data = {
            "document_type": "printed",
            "vendor": {"name": "Test Diagnostic Lab", "phone": "0300-1111111"},
            "customer": {"name": "Zainab Bibi", "phone": "0321-9998887"},
            "invoice_no": "LAB-7788",
            "date": "2026-10-14",
            "subtotal": 1500.0,
            "grand_total": 1500.0,
            "items": [
                {
                    "name": "Blood Complete Picture",
                    "quantity": 1,
                    "unit_price": 1500.0,
                    "line_total": 1500.0,
                }
            ],
        }

        class MockCustomerExtractor:
            last_token_count = 100

            def extract(self, *files):
                return custom_data

        monkeypatch.setattr(
            "scanning.services.extraction.get_ai_extractor",
            lambda *args, **kwargs: MockCustomerExtractor(),
        )

        job = ScanJob.objects.create(
            provider="mock",
            created_by=superadmin_user,
        )
        BillFile.objects.create(
            scan_job=job,
            file=sample_image,
            page_number=1,
            file_hash="lab_hash_7788",
        )

        bill = process_scan_job(job)
        assert bill is not None

        # 1. Customer profile must be auto-created in Party table
        customer_party = Party.objects.filter(name="Zainab Bibi", party_type="customer").first()
        assert customer_party is not None, "Customer Party profile was not auto-created!"
        assert customer_party.phone == "0321-9998887"

        # 2. Bill notes must record customer information
        assert "Zainab Bibi" in bill.notes

    def test_review_view_supports_customer_and_sale_toggle(
        self, monkeypatch, client, superadmin_user, sample_image
    ):
        """Review screen displays extracted customer details and supports setting bill_type to Sale with customer party."""
        from parties.models import Party
        from scanning.models import BillFile, ScanJob
        from scanning.services.extraction import process_scan_job

        custom_data = {
            "document_type": "printed",
            "vendor": {"name": "Alpha Clinic", "phone": "0300-2223334"},
            "customer": {"name": "Tariq Mahmood", "phone": "0333-5556667"},
            "invoice_no": "INV-CLINIC-1",
            "date": "2026-10-14",
            "subtotal": 800.0,
            "grand_total": 800.0,
            "items": [{"name": "Checkup", "quantity": 1, "unit_price": 800.0, "line_total": 800.0}],
        }

        class MockCustomerExtractor:
            last_token_count = 100

            def extract(self, *files):
                return custom_data

        monkeypatch.setattr(
            "scanning.services.extraction.get_ai_extractor",
            lambda *args, **kwargs: MockCustomerExtractor(),
        )

        job = ScanJob.objects.create(
            provider="mock",
            created_by=superadmin_user,
        )
        BillFile.objects.create(
            scan_job=job,
            file=sample_image,
            page_number=1,
            file_hash="clinic_hash_1",
        )
        bill = process_scan_job(job)

        client.force_login(superadmin_user)
        # GET review view must pass extracted customer details
        get_resp = client.get(f"/en/scanning/review/{job.pk}/")
        assert get_resp.status_code == 200
        assert "Tariq Mahmood" in get_resp.context["extracted_customer_name"]

        # POST review view with bill_type='sale'
        cust_party = Party.objects.filter(name="Tariq Mahmood", party_type="customer").first()
        assert cust_party is not None
        post_resp = client.post(
            f"/en/scanning/review/{job.pk}/",
            {
                "action": "verify",
                "bill_type": "sale",
                "party": cust_party.pk,
                "customer_name": "Tariq Mahmood",
                "customer_phone": "0333-5556667",
                "invoice_no": "INV-CLINIC-1",
                "bill_date": "2026-10-14",
            },
        )
        assert post_resp.status_code == 302
        bill.refresh_from_db()
        assert bill.bill_type == "sale"
        assert bill.party == cust_party

    def test_missing_item_price_detected_as_error(self):
        """Line item with missing or 0.00 unit price and line total is flagged as error."""
        from scanning.services.validation import detect_bill_errors

        extracted_data = {
            "invoice_no": "INV-MISSING-PRICE",
            "date": "2026-10-13",
            "subtotal": 100.0,
            "grand_total": 100.0,
            "items": [
                {
                    "name": "Missing Price Item",
                    "quantity": 1,
                    "unit_price": 0.0,
                    "line_total": 0.0,
                }
            ],
        }
        errors = detect_bill_errors(extracted_data)
        missing_price_errs = [e for e in errors if e.get("field_name") == "unit_price"]
        assert len(missing_price_errs) >= 1
        assert "missing price" in missing_price_errs[0]["message"].lower()

    def test_bill_is_total_invalid_properties(self, db):
        """Bill model correctly reports has_calculation_error, has_missing_price, and is_total_invalid."""
        from bills.models import Bill, BillItem
        from parties.models import Party

        party = Party.objects.create(name="Test Supplier", party_type=Party.PartyType.VENDOR)

        # Valid bill
        bill = Bill.objects.create(
            party=party,
            invoice_no="INV-VALID-TOTAL",
            bill_date=timezone.now().date(),
            subtotal=Decimal("200.00"),
            grand_total=Decimal("200.00"),
        )
        BillItem.objects.create(
            bill=bill,
            item_name="Item A",
            quantity=Decimal("2"),
            unit_price=Decimal("100.00"),
            line_total=Decimal("200.00"),
        )
        assert not bill.is_total_invalid
        assert not bill.has_calculation_error
        assert not bill.has_missing_price

        # Mismatch in grand total
        bill.grand_total = Decimal("250.00")
        assert bill.has_calculation_error
        assert bill.is_total_invalid

        # Missing price on item
        bill.grand_total = Decimal("200.00")
        BillItem.objects.create(
            bill=bill,
            item_name="Item Without Price",
            quantity=Decimal("1"),
            unit_price=Decimal("0.00"),
            line_total=Decimal("0.00"),
        )
        assert bill.has_missing_price
        assert bill.is_total_invalid

    def test_review_page_displays_red_total_when_mismatched(self, client, superadmin_user):
        """Review page applies red styling to Grand Total when items mismatch slip total."""
        from bills.models import Bill, BillItem
        from parties.models import Party
        from scanning.models import ScanJob

        party = Party.objects.create(name="Test Vendor 2", party_type=Party.PartyType.VENDOR)

        bill = Bill.objects.create(
            party=party,
            invoice_no="INV-MISMATCH-REVIEW",
            bill_date=timezone.now().date(),
            subtotal=Decimal("2676.00"),
            grand_total=Decimal("2670.00"),  # Mismatch (slip has 2670, items sum 2676)
        )
        BillItem.objects.create(
            bill=bill,
            item_name="Test Product",
            quantity=Decimal("1"),
            unit_price=Decimal("2676.00"),
            line_total=Decimal("2676.00"),
        )
        job = ScanJob.objects.create(
            bill=bill,
            provider="mock",
            status=ScanJob.Status.COMPLETED,
            extracted_data={"grand_total": 2670.00},
        )

        client.force_login(superadmin_user)
        response = client.get(f"/en/scanning/review/{job.pk}/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "text-red-600" in content
        assert response.context["is_total_invalid"] is True

    def test_review_page_post_updates_item_price_and_recalculates(self, client, superadmin_user):
        """Posting edited item prices from the review page updates line items and recalculates totals."""
        from bills.models import Bill, BillItem
        from parties.models import Party
        from scanning.models import ScanJob

        party = Party.objects.create(name="Test Vendor 3", party_type=Party.PartyType.VENDOR)

        bill = Bill.objects.create(
            party=party,
            invoice_no="INV-EDIT-ITEMS",
            bill_date=timezone.now().date(),
            subtotal=Decimal("0.00"),
            grand_total=Decimal("0.00"),
        )
        item = BillItem.objects.create(
            bill=bill,
            item_name="Chicken",
            quantity=Decimal("1.00"),
            unit_price=Decimal("0.00"),  # Missing price
            line_total=Decimal("0.00"),
        )
        job = ScanJob.objects.create(bill=bill, provider="mock", status=ScanJob.Status.COMPLETED)

        client.force_login(superadmin_user)
        post_data = {
            "action": "save_draft",
            "invoice_no": "INV-EDIT-ITEMS",
            "party": str(party.pk),
            "bill_date": str(timezone.now().date()),
            "discount": "0.00",
            "tax": "0.00",
            "item_id": [str(item.pk)],
            f"item_name_{item.pk}": "Chicken 1kg",
            f"item_qty_{item.pk}": "1",
            f"item_price_{item.pk}": "450.00",
        }
        response = client.post(f"/en/scanning/review/{job.pk}/", post_data)
        assert response.status_code == 302

        item.refresh_from_db()
        bill.refresh_from_db()
        assert item.unit_price == Decimal("450.00")
        assert item.line_total == Decimal("450.00")
        assert bill.grand_total == Decimal("450.00")

    def test_review_page_action_correct_and_go(self, client, superadmin_user):
        """Action 'correct_and_go' updates grand_total to computed items sum, marks verified, and approves bill."""
        from bills.models import Bill, BillItem
        from parties.models import Party
        from scanning.models import BillError, ScanJob

        party = Party.objects.create(name="Vendor Math Test", party_type=Party.PartyType.VENDOR)
        bill = Bill.objects.create(
            party=party,
            invoice_no="INV-MATH-CORRECT",
            bill_date=timezone.now().date(),
            subtotal=Decimal("2670.00"),
            grand_total=Decimal("2670.00"),
            status=Bill.Status.NEEDS_REVIEW,
        )
        item = BillItem.objects.create(
            bill=bill,
            item_name="Item 1",
            quantity=Decimal("1"),
            unit_price=Decimal("2676.00"),
            line_total=Decimal("2676.00"),
        )
        err = BillError.objects.create(
            bill=bill,
            error_type="math_mismatch",
            message="Items total 2676.00 != Grand total 2670.00",
            is_resolved=False,
        )
        job = ScanJob.objects.create(bill=bill, provider="mock", status=ScanJob.Status.COMPLETED)

        client.force_login(superadmin_user)
        post_data = {
            "action": "correct_and_go",
            "invoice_no": "INV-MATH-CORRECT",
            "party": str(party.pk),
            "bill_date": str(timezone.now().date()),
            "discount": "0.00",
            "tax": "0.00",
            "item_id": [str(item.pk)],
            f"item_name_{item.pk}": "Item 1",
            f"item_qty_{item.pk}": "1",
            f"item_price_{item.pk}": "2676.00",
        }
        response = client.post(f"/en/scanning/review/{job.pk}/", post_data)
        assert response.status_code == 302

        bill.refresh_from_db()
        err.refresh_from_db()
        assert bill.grand_total == Decimal("2676.00")
        assert bill.has_discrepancy is False
        assert bill.status == Bill.Status.VERIFIED
        assert err.is_resolved is True

    def test_review_page_action_accept_incorrect(self, client, superadmin_user):
        """Action 'accept_incorrect' keeps slip total, sets has_discrepancy=True, logs reason, and verifies bill."""
        from bills.models import Bill, BillItem
        from parties.models import Party
        from scanning.models import ScanJob

        party = Party.objects.create(name="Customer Math Test", party_type=Party.PartyType.CUSTOMER)
        bill = Bill.objects.create(
            party=party,
            invoice_no="INV-MATH-INCORRECT",
            bill_date=timezone.now().date(),
            subtotal=Decimal("2670.00"),
            grand_total=Decimal("2670.00"),
            status=Bill.Status.NEEDS_REVIEW,
        )
        item = BillItem.objects.create(
            bill=bill,
            item_name="Item 1",
            quantity=Decimal("1"),
            unit_price=Decimal("2676.00"),
            line_total=Decimal("2676.00"),
        )
        job = ScanJob.objects.create(bill=bill, provider="mock", status=ScanJob.Status.COMPLETED)

        client.force_login(superadmin_user)
        post_data = {
            "action": "accept_incorrect",
            "invoice_no": "INV-MATH-INCORRECT",
            "party": str(party.pk),
            "bill_date": str(timezone.now().date()),
            "discount": "0.00",
            "tax": "0.00",
            "grand_total": "2670.00",
            "item_id": [str(item.pk)],
            f"item_name_{item.pk}": "Item 1",
            f"item_qty_{item.pk}": "1",
            f"item_price_{item.pk}": "2676.00",
        }
        response = client.post(f"/en/scanning/review/{job.pk}/", post_data)
        assert response.status_code == 302

        bill.refresh_from_db()
        assert bill.grand_total == Decimal("2670.00")
        assert bill.original_slip_total == Decimal("2670.00")
        assert bill.has_discrepancy is True
        assert "Paper slip total was PKR 2670.00" in bill.discrepancy_reason
        assert bill.status == Bill.Status.VERIFIED

    def test_review_page_multi_page_viewer(self, client, superadmin_user):
        """Review page renders interactive multi-page viewer and thumbnail switchers for all pages."""
        from bills.models import Bill
        from parties.models import Party
        from scanning.models import BillFile, ScanJob

        party = Party.objects.create(name="Multi Page Vendor", party_type=Party.PartyType.VENDOR)
        bill = Bill.objects.create(
            party=party,
            invoice_no="INV-MULTI-PAGE",
            bill_date=timezone.now().date(),
            grand_total=Decimal("1000.00"),
            status=Bill.Status.NEEDS_REVIEW,
        )
        job = ScanJob.objects.create(bill=bill, provider="mock", status=ScanJob.Status.COMPLETED)

        # Create 2 uploaded bill files (pages)
        BillFile.objects.create(
            scan_job=job,
            bill=bill,
            file="bills/page1.jpg",
            page_number=1,
            file_type=BillFile.FileType.IMAGE,
        )
        BillFile.objects.create(
            scan_job=job,
            bill=bill,
            file="bills/page2.jpg",
            page_number=2,
            file_type=BillFile.FileType.IMAGE,
        )

        client.force_login(superadmin_user)
        response = client.get(f"/en/scanning/review/{job.pk}/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")

        # Both pages should be rendered with index switches
        assert "Page 1" in content
        assert "Page 2" in content
        assert "currentIndex = 0" in content
        assert "currentIndex = 1" in content
        assert "page1.jpg" in content
        assert "page2.jpg" in content
        assert "Click to view page" in content

    def test_file_preview_view_renders_preview(self, client, superadmin_user, sample_image):
        """file_preview_view returns HTTP 200 with image content and SAMEORIGIN frame options."""
        from bills.models import Bill
        from parties.models import Party
        from scanning.models import BillFile, ScanJob

        party = Party.objects.create(name="Preview Vendor", party_type=Party.PartyType.VENDOR)
        bill = Bill.objects.create(party=party, invoice_no="INV-PREVIEW-01")
        job = ScanJob.objects.create(bill=bill, status=ScanJob.Status.COMPLETED)
        bf = BillFile.objects.create(
            scan_job=job,
            bill=bill,
            file=sample_image,
            page_number=1,
            file_type=BillFile.FileType.IMAGE,
        )

        client.force_login(superadmin_user)
        response = client.get(f"/en/scanning/file-preview/{bf.pk}/")
        assert response.status_code == 200
        assert "image/" in response.headers.get("Content-Type", "")
        assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"

    def test_retail_savings_and_fbr_service_fee_normalization(self):
        """Verify retail POS saving amount adds to item price, deducts at end as discount, and adds FBR Service Fee."""
        from scanning.services.extraction import validate_extraction_schema

        raw_data = {
            "document_type": "printed",
            "vendor": {"name": "Euro Store"},
            "items": [
                {
                    "name": "BUNNYS MILKY BREAD LARGE",
                    "quantity": 1,
                    "unit_price": 190.0,
                    "line_total": 190.0,
                    "discount": 40.0,
                },
                {
                    "name": "EURO EGG 6 PCS",
                    "quantity": 1,
                    "unit_price": 132.0,
                    "line_total": 132.0,
                    "discount": 0.0,
                },
                {
                    "name": "BAG SMALL",
                    "quantity": 1,
                    "unit_price": 10.0,
                    "line_total": 10.0,
                    "discount": 0.0,
                },
            ],
            "subtotal": 333.0,
            "discount": 40.0,
            "tax": 0.0,
            "grand_total": 333.0,
        }

        normalized = validate_extraction_schema(raw_data)
        # FBR Service Fee (1.00 PKR) auto-detected
        assert normalized["tax"] == 1.0
        # Saving (40.00) added to item price (190 + 40 = 230)
        assert normalized["items"][0]["unit_price"] == 230.0
        assert normalized["items"][0]["line_total"] == 230.0
        # Subtotal equals pre-discount actual sum (230 + 132 + 10 = 372)
        assert normalized["subtotal"] == 372.0
        # Discount deducted at end
        assert normalized["discount"] == 40.0
        # Grand total reconciles: 372 - 40 + 1 = 333
        assert (
            normalized["subtotal"] - normalized["discount"] + normalized["tax"]
            == normalized["grand_total"]
        )

    def test_zero_price_items_not_treated_as_missing_when_total_matches(
        self, client, superadmin_user
    ):
        """Zero-priced items (e.g. waived fees, free items) on balanced bills are not treated as missing price."""
        from decimal import Decimal

        from bills.models import Bill, BillItem
        from parties.models import Party
        from scanning.models import ScanJob
        from scanning.services.validation import detect_bill_errors

        # 1. Validation service check
        extracted_data = {
            "document_type": "fee_challan",
            "subtotal": 3500.0,
            "grand_total": 3500.0,
            "items": [
                {"name": "Tuition fee", "quantity": 1, "unit_price": 3250.0, "line_total": 3250.0},
                {"name": "Registration fee", "quantity": 1, "unit_price": 0.0, "line_total": 0.0},
                {"name": "Generator fee", "quantity": 1, "unit_price": 0.0, "line_total": 0.0},
                {"name": "Others", "quantity": 1, "unit_price": 200.0, "line_total": 200.0},
                {"name": "Arrears", "quantity": 1, "unit_price": 50.0, "line_total": 50.0},
            ],
        }
        errors = detect_bill_errors(extracted_data)
        missing_price_errs = [e for e in errors if e.get("field_name") == "unit_price"]
        assert (
            len(missing_price_errs) == 0
        ), f"Expected 0 missing price errors, got {missing_price_errs}"

        # 2. Model property check
        party = Party.objects.create(name="School System", party_type=Party.PartyType.VENDOR)
        bill = Bill.objects.create(
            party=party,
            invoice_no="CHALLAN-001",
            bill_date=timezone.now().date(),
            subtotal=Decimal("3500.00"),
            grand_total=Decimal("3500.00"),
            status=Bill.Status.NEEDS_REVIEW,
        )
        for it in extracted_data["items"]:
            BillItem.objects.create(
                bill=bill,
                item_name=it["name"],
                quantity=Decimal(str(it["quantity"])),
                unit_price=Decimal(str(it["unit_price"])),
                line_total=Decimal(str(it["line_total"])),
            )

        assert not bill.has_missing_price
        assert not bill.is_total_invalid

        # 3. Review view check
        job = ScanJob.objects.create(
            bill=bill,
            provider="mock",
            status=ScanJob.Status.COMPLETED,
            extracted_data=extracted_data,
        )
        client.force_login(superadmin_user)
        response = client.get(f"/en/scanning/review/{job.pk}/")
        assert response.status_code == 200
        assert response.context["has_missing_price"] is False
        assert response.context["is_total_invalid"] is False
        content = response.content.decode("utf-8")
        assert '<span id="total-badge"' not in content

    def test_fee_challan_blank_arrears_row_not_assigned_grand_total(self):
        """When an arrears/arreras row is physically adjacent to Grand Total on a fee challan and blank on the slip,
        it must not inherit the Grand Total when the bill items already balance."""
        from scanning.services.extraction import validate_extraction_schema

        raw_data = {
            "document_type": "fee_challan",
            "vendor": {"name": "The Smart School"},
            "invoice_no": "1707",
            "date": "2026-10-14",
            "items": [
                {"name": "Registration fee", "line_total": 0.0, "unit_price": 0.0, "quantity": 1},
                {"name": "Admission fee", "line_total": 0.0, "unit_price": 0.0, "quantity": 1},
                {"name": "Tuition fee", "line_total": 0.0, "unit_price": 0.0, "quantity": 1},
                {"name": "Generator fee", "line_total": 0.0, "unit_price": 0.0, "quantity": 1},
                {"name": "Annual funds", "line_total": 5000.0, "unit_price": 5000.0, "quantity": 1},
                {"name": "Others", "line_total": 0.0, "unit_price": 0.0, "quantity": 1},
                {"name": "Arreras", "line_total": 5000.0, "unit_price": 5000.0, "quantity": 1},
            ],
            "subtotal": 10000.0,
            "discount": 0.0,
            "tax": 0.0,
            "grand_total": 5000.0,
        }

        validated = validate_extraction_schema(raw_data)
        arreras_item = next(it for it in validated["items"] if "arrer" in it["name"].lower())
        assert arreras_item["line_total"] == 0.0
        assert arreras_item["unit_price"] == 0.0
        assert validated["subtotal"] == 5000.0
        assert validated["grand_total"] == 5000.0

    def test_upload_view_renders_direct_camera_capture_input(self, client, superadmin_user):
        """Upload view includes direct camera capture attribute and camera trigger."""
        client.force_login(superadmin_user)
        response = client.get("/en/scanning/upload/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'capture="environment"' in content
        assert 'id="camera-capture-input"' in content
        assert "Take Photo" in content

    def test_upload_view_renders_urdu_camera_label(self, client, superadmin_user):
        """When viewing in Urdu, upload screen displays Urdu camera shortcut labels."""
        client.force_login(superadmin_user)
        response = client.get("/ur/scanning/upload/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert 'capture="environment"' in content
        assert "کیمرہ سے تصویر لیں" in content

    def test_dashboard_renders_direct_camera_shortcut_link(self, client, superadmin_user):
        """Dashboard renders direct camera shortcut link with ?camera=1."""
        client.force_login(superadmin_user)
        response = client.get("/en/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "upload/?camera=1" in content

    def test_review_view_discard_action_soft_deletes_and_redirects(self, client, superadmin_user):
        """POST action='discard' soft-deletes the bill, marks scan job failed, and redirects to upload."""
        from bills.models import Bill
        from scanning.models import BillEditHistory, BillError, ScanJob

        party = Party.objects.create(name="Discard Vendor", party_type=Party.PartyType.VENDOR)
        bill = Bill.objects.create(
            party=party,
            invoice_no="INV-DISCARD-1",
            bill_date=timezone.now().date(),
            grand_total=Decimal("500.00"),
            status=Bill.Status.NEEDS_REVIEW,
        )
        job = ScanJob.objects.create(
            bill=bill,
            provider="mock",
            status=ScanJob.Status.COMPLETED,
        )
        err = BillError.objects.create(
            bill=bill,
            error_type=BillError.ErrorType.MATH_MISMATCH,
            message="Math mismatch test",
            is_resolved=False,
        )

        client.force_login(superadmin_user)
        response = client.post(
            f"/en/scanning/review/{job.pk}/",
            {"action": "discard"},
        )
        assert response.status_code == 302
        assert response.url == "/en/scanning/upload/"

        bill.refresh_from_db()
        assert bill.is_deleted is True
        assert bill.deleted_at is not None

        job.refresh_from_db()
        assert job.status == ScanJob.Status.FAILED
        assert "discarded by user" in job.error_message

        err.refresh_from_db()
        assert err.is_resolved is True

        history = BillEditHistory.objects.filter(bill=bill, new_value="discarded")
        assert history.exists()

    def test_review_view_discarded_bill_excluded_from_pending_queries(
        self, client, superadmin_user
    ):
        """A discarded bill does not appear in pending bills filter for dashboard."""
        from bills.models import Bill
        from scanning.models import ScanJob

        party = Party.objects.create(name="Discard Vendor 2", party_type=Party.PartyType.VENDOR)
        bill = Bill.objects.create(
            party=party,
            invoice_no="INV-DISCARD-2",
            bill_date=timezone.now().date(),
            grand_total=Decimal("750.00"),
            status=Bill.Status.NEEDS_REVIEW,
        )
        job = ScanJob.objects.create(
            bill=bill,
            provider="mock",
            status=ScanJob.Status.COMPLETED,
        )

        pending = Bill.objects.filter(
            is_deleted=False, status__in=[Bill.Status.NEEDS_REVIEW, Bill.Status.DRAFT]
        )
        assert bill in pending

        client.force_login(superadmin_user)
        client.post(f"/en/scanning/review/{job.pk}/", {"action": "discard"})

        pending_after = Bill.objects.filter(
            is_deleted=False, status__in=[Bill.Status.NEEDS_REVIEW, Bill.Status.DRAFT]
        )
        assert bill not in pending_after

    def test_review_view_renders_discard_buttons_in_urdu(
        self, client, superadmin_user, sample_image
    ):
        """Review page in Urdu renders the 'بل رد کریں' discard button."""
        from scanning.models import BillFile, ScanJob
        from scanning.services.extraction import process_scan_job

        job = ScanJob.objects.create(provider="mock", created_by=superadmin_user)
        BillFile.objects.create(scan_job=job, file=sample_image, page_number=1)
        process_scan_job(job)

        client.force_login(superadmin_user)
        response = client.get(f"/ur/scanning/review/{job.pk}/")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "بل رد کریں" in content
