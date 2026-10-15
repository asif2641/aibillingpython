"""scanning/services/image_processing.py
======================================
Image validation, EXIF auto-rotation, downscaling, format conversion,
and pre-AI document quality assessment (blur, dark/low light, blank page, and minimum dimensions).
"""

import hashlib
import io
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageFilter, ImageOps, ImageStat

MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_DIMENSION = 2048
MIN_DIMENSION = 100  # Minimum 100px width/height for legible bills
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf"}

# Image Quality Assessment Thresholds
DARK_THRESHOLD_MEAN = 35.0  # Mean luminance < 35 indicates pitch black / severely underexposed
BLANK_THRESHOLD_STDDEV = 3.5  # Stddev of luminance < 3.5 indicates blank/uniform sheet with no text
BLUR_THRESHOLD_VAR = 5.0  # Edge variance < 5.0 on cropped Sobel/FIND_EDGES indicates heavy blur

URDU_QUALITY_MESSAGES = {
    "too_small": "تصویر کا سائز بہت چھوٹا ہے (100 پکسل سے کم)۔ براہ کرم واضح اور بڑے سائز کی دستاویز اپلوڈ کریں۔",
    "too_dark": "تصویر میں بہت زیادہ اندھیرا ہے اور بل پڑھا نہیں جا رہا۔ براہ کرم بہتر روشنی میں دوبارہ تصویر بنائیں۔",
    "blank_page": "تصویر خالی صفحہ معلوم ہوتی ہے جس پر کوئی بل یا تحریر موجود نہیں۔ براہ کرم درست بل اپلوڈ کریں۔",
    "blurry": "تصویر بہت زیادہ دھندلی ہے اور الفاظ واضح نہیں ہیں۔ براہ کرم فوکس کر کے صاف تصویر اپلوڈ کریں۔",
}

ENGLISH_QUALITY_MESSAGES = {
    "too_small": _(
        "Image is too small (under 100px) to be a legible bill. Please upload a higher resolution document."
    ),
    "too_dark": _(
        "Image is too dark or poorly lit to read clearly. Please retake the photo with adequate lighting."
    ),
    "blank_page": _(
        "Image appears to be blank or has no readable bill content. Please upload a valid bill."
    ),
    "blurry": _(
        "Image is too blurry for AI to read text accurately. Please retake a sharp, focused photo."
    ),
}


@dataclass
class ImageQualityReport:
    """Report detailing image quality inspection metrics and findings."""

    is_valid: bool
    issue_code: Optional[str]  # "too_small", "too_dark", "blank_page", "blurry"
    error_message: str
    metrics: Dict[str, Any]


def get_quality_error_message(issue_code: str) -> str:
    """Return bilingual quality alert based on the active language."""
    lang = (get_language() or "en").lower()
    if lang.startswith("ur") and issue_code in URDU_QUALITY_MESSAGES:
        return URDU_QUALITY_MESSAGES[issue_code]
    return str(
        ENGLISH_QUALITY_MESSAGES.get(
            issue_code, _("Image quality is insufficient for accurate AI reading.")
        )
    )


def assess_image_quality(img: Image.Image) -> ImageQualityReport:
    """Inspect image dimensions, illumination, contrast, and focus before sending to AI.

    Prevents unnecessary AI token usage and scanning failures on defective inputs.
    Checks:
      1. Minimum dimensions (>= 100px)
      2. Low light / Too dark (mean luminance >= 35)
      3. Blank page / solid color (contrast stddev >= 3.5)
      4. Blurry / Out of focus (edge variance and sharpness ratio)
    """
    w, h = img.size
    metrics: Dict[str, Any] = {"width": float(w), "height": float(h)}

    # 1. Dimension Check: Must be at least 100x100px
    if w < MIN_DIMENSION or h < MIN_DIMENSION:
        return ImageQualityReport(
            is_valid=False,
            issue_code="too_small",
            error_message=get_quality_error_message("too_small"),
            metrics=metrics,
        )

    # Standardize evaluation size to max 1000px for consistent metric calculation
    eval_img = img.copy()
    if eval_img.width > 1000 or eval_img.height > 1000:
        eval_img.thumbnail((1000, 1000), Image.Resampling.BILINEAR)

    gray = eval_img.convert("L")
    stat = ImageStat.Stat(gray)
    mean_brightness = float(stat.mean[0])
    contrast_stddev = float(stat.stddev[0])
    metrics["mean_brightness"] = mean_brightness
    metrics["contrast_stddev"] = contrast_stddev

    # 2. Too Dark / Low Light Check
    if mean_brightness < DARK_THRESHOLD_MEAN:
        return ImageQualityReport(
            is_valid=False,
            issue_code="too_dark",
            error_message=get_quality_error_message("too_dark"),
            metrics=metrics,
        )

    # 3. Blank Page / Uniform Background Check
    if contrast_stddev < BLANK_THRESHOLD_STDDEV:
        return ImageQualityReport(
            is_valid=False,
            issue_code="blank_page",
            error_message=get_quality_error_message("blank_page"),
            metrics=metrics,
        )

    # 4. Blur / Sharpness Check
    # Crop 2-pixel border to eliminate filter boundary artifacts
    edges = gray.filter(ImageFilter.FIND_EDGES)
    cropped_edges = edges.crop((2, 2, max(3, eval_img.width - 2), max(3, eval_img.height - 2)))
    estat = ImageStat.Stat(cropped_edges)
    edge_var = float(estat.var[0])
    edge_mean = float(estat.mean[0])
    metrics["edge_var"] = edge_var
    metrics["edge_mean"] = edge_mean

    # Sharpness ratio: edge variance relative to overall contrast
    sharpness_ratio = edge_var / (contrast_stddev + 0.1)
    metrics["sharpness_ratio"] = sharpness_ratio

    if edge_var < BLUR_THRESHOLD_VAR and sharpness_ratio < 1.0:
        return ImageQualityReport(
            is_valid=False,
            issue_code="blurry",
            error_message=get_quality_error_message("blurry"),
            metrics=metrics,
        )

    return ImageQualityReport(
        is_valid=True,
        issue_code=None,
        error_message="",
        metrics=metrics,
    )


def validate_and_preprocess_file(
    file_obj: UploadedFile, check_quality: bool = True
) -> Tuple[bytes, str, str]:
    """Validate file size, extension, dimensions, illumination, and focus,
    then clean up, orient, and downscale images.

    Returns:
        (processed_bytes, file_type, file_hash)
    Raises:
        ValidationError if file is oversized, unsupported, corrupted, too small,
        too dark, blank, or blurry.
    """
    # 1. Size check
    file_size = getattr(file_obj, "size", 0)
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValidationError(
            f"File size ({file_size / (1024 * 1024):.1f} MB) exceeds the 15 MB limit. Please compress the file."
        )

    # 2. Extension check
    filename = getattr(file_obj, "name", "")
    _, ext = os.path.splitext(filename.lower())
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"Unsupported file format '{ext}'. Please upload an image (JPG, PNG, WEBP) or PDF."
        )

    # Read raw content bytes
    if hasattr(file_obj, "seek"):
        file_obj.seek(0)
    content_bytes = file_obj.read()
    if hasattr(file_obj, "seek"):
        file_obj.seek(0)

    # Double-check byte length
    if len(content_bytes) > MAX_FILE_SIZE_BYTES:
        raise ValidationError("File size exceeds the 15 MB limit.")

    # 3. Handle PDF documents (vector text or multi-page documents)
    if ext == ".pdf":
        hasher = hashlib.sha256(content_bytes)
        return content_bytes, "pdf", hasher.hexdigest()

    # 4. Handle Images (Pillow)
    try:
        img = Image.open(io.BytesIO(content_bytes))
        # Handle EXIF orientation
        img = ImageOps.exif_transpose(img)

        # Pre-AI Quality Assessment (blurry, dark, blank, too small)
        if check_quality:
            quality_report = assess_image_quality(img)
            if not quality_report.is_valid:
                raise ValidationError(quality_report.error_message)

        # Scale down if dimensions exceed 2048px bounding box
        if img.width > MAX_DIMENSION or img.height > MAX_DIMENSION:
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

        # Ensure standard RGB for JPEG output
        output_format = "JPEG"
        if img.mode in ("RGBA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                bg.paste(img, mask=img.split()[3])
            else:
                bg.paste(img)
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        out_buf = io.BytesIO()
        img.save(out_buf, format=output_format, quality=85, optimize=True)
        processed_bytes = out_buf.getvalue()

        raw_hash = hashlib.sha256(content_bytes).hexdigest()
        return processed_bytes, "image", raw_hash
    except Exception as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError(f"Unable to process image: {exc}") from exc
