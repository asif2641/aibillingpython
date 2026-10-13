"""scanning/services/image_processing.py
======================================
Image validation, EXIF auto-rotation, downscaling, and format conversion.
"""

import hashlib
import io
import os
from typing import Tuple

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from PIL import Image, ImageOps

MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_DIMENSION = 2048
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf"}


def validate_and_preprocess_file(file_obj: UploadedFile) -> Tuple[bytes, str, str]:
    """Validate file size and extension, then clean up, orient, and downscale images.

    Returns:
        (processed_bytes, file_type, file_hash)
    Raises:
        ValidationError if file is oversized, unsupported, or corrupted.
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

    # 3. Handle PDF documents
    if ext == ".pdf":
        hasher = hashlib.sha256(content_bytes)
        return content_bytes, "pdf", hasher.hexdigest()

    # 4. Handle Images (Pillow)
    try:
        img = Image.open(io.BytesIO(content_bytes))
        # Handle EXIF orientation
        img = ImageOps.exif_transpose(img)

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

        hasher = hashlib.sha256(processed_bytes)
        return processed_bytes, "image", hasher.hexdigest()
    except Exception as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError(f"Unable to process image: {exc}") from exc
