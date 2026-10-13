"""scanning/models.py
==================
Models for AI bill scanning, uploaded files, scan jobs, error detection, and audit history.
"""

import contextlib
import hashlib

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from bills.models import Bill


class BillFile(models.Model):
    """Uploaded image or PDF document associated with a bill or scan job."""

    class FileType(models.TextChoices):
        IMAGE = "image", _("Image")
        PDF = "pdf", _("PDF")

    bill = models.ForeignKey(
        Bill,
        on_delete=models.CASCADE,
        related_name="files",
        null=True,
        blank=True,
        verbose_name=_("associated bill"),
    )
    scan_job = models.ForeignKey(
        "ScanJob",
        on_delete=models.CASCADE,
        related_name="files",
        null=True,
        blank=True,
        verbose_name=_("associated scan job"),
    )
    file = models.FileField(
        upload_to="bills/%Y/%m/",
        verbose_name=_("uploaded file"),
    )
    page_number = models.PositiveIntegerField(
        default=1,
        verbose_name=_("page number"),
    )
    file_type = models.CharField(
        max_length=20,
        choices=FileType.choices,
        default=FileType.IMAGE,
        verbose_name=_("file type"),
    )
    file_size = models.PositiveIntegerField(
        default=0,
        verbose_name=_("file size in bytes"),
    )
    file_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("SHA-256 hash"),
        help_text=_("Hex digest of file contents for duplicate detection."),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("uploaded at"),
    )

    class Meta:
        verbose_name = _("bill file")
        verbose_name_plural = _("bill files")
        ordering = ["page_number", "id"]

    def __str__(self) -> str:
        return f"File #{self.pk} (Page {self.page_number})"

    def save(self, *args, **kwargs) -> None:
        """Compute SHA-256 hash and record size if file is provided and hash is unset."""
        if self.file and not self.file_hash:
            with contextlib.suppress(OSError, ValueError, AttributeError):
                hasher = hashlib.sha256()
                if hasattr(self.file, "chunks"):
                    for chunk in self.file.chunks():
                        hasher.update(chunk)
                else:
                    pos = self.file.tell() if hasattr(self.file, "tell") else 0
                    self.file.seek(0)
                    hasher.update(self.file.read())
                    self.file.seek(pos)
                self.file_hash = hasher.hexdigest()
                self.file_size = self.file.size
        super().save(*args, **kwargs)


class ScanJob(models.Model):
    """Background or synchronous processing job for an AI document scan."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PROCESSING = "processing", _("Processing")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")

    bill = models.ForeignKey(
        Bill,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scan_jobs",
        verbose_name=_("resulting bill"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name=_("processing status"),
    )
    provider = models.CharField(
        max_length=50,
        default="mock",
        verbose_name=_("AI provider"),
    )
    model_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("model name"),
    )
    raw_response = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("raw AI response"),
    )
    extracted_data = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("extracted JSON data"),
    )
    error_message = models.TextField(
        blank=True,
        default="",
        verbose_name=_("error message if failed"),
    )
    token_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("tokens used"),
    )
    latency_ms = models.PositiveIntegerField(
        default=0,
        verbose_name=_("processing latency in ms"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("user who initiated scan"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("created at"),
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("completed at"),
    )

    class Meta:
        verbose_name = _("scan job")
        verbose_name_plural = _("scan jobs")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"ScanJob #{self.pk} ({self.get_status_display()})"


class BillError(models.Model):
    """Discrepancies, math mismatch, missing fields, or duplicate alerts for a bill."""

    class ErrorType(models.TextChoices):
        MATH_MISMATCH = "math_mismatch", _("Math Mismatch")
        SUBTOTAL_MISMATCH = "subtotal_mismatch", _("Subtotal Mismatch")
        GRAND_TOTAL_MISMATCH = "grand_total_mismatch", _("Grand Total Mismatch")
        MISSING_FIELD = "missing_field", _("Missing Critical Field")
        DATE_ANOMALY = "date_anomaly", _("Date Anomaly")
        DUPLICATE_SUSPECT = "duplicate_suspect", _("Duplicate Suspect")
        LOW_CONFIDENCE = "low_confidence", _("Low Confidence Field")

    class Severity(models.TextChoices):
        WARNING = "warning", _("Warning")
        ERROR = "error", _("Error")

    bill = models.ForeignKey(
        Bill,
        on_delete=models.CASCADE,
        related_name="errors",
        verbose_name=_("bill"),
    )
    error_type = models.CharField(
        max_length=50,
        choices=ErrorType.choices,
        verbose_name=_("error type"),
    )
    field_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("affected field"),
    )
    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.WARNING,
        verbose_name=_("severity"),
    )
    message = models.TextField(
        verbose_name=_("issue description"),
    )
    suggested_fix = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("suggested fix payload"),
    )
    is_resolved = models.BooleanField(
        default=False,
        verbose_name=_("resolved"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("detected at"),
    )

    class Meta:
        verbose_name = _("bill error")
        verbose_name_plural = _("bill errors")
        ordering = ["is_resolved", "-created_at"]

    def __str__(self) -> str:
        status = "Resolved" if self.is_resolved else "Active"
        return f"[{self.get_severity_display()}] {self.message} ({status})"


class BillEditHistory(models.Model):
    """Audit log tracking field modifications, previous values, and editors."""

    bill = models.ForeignKey(
        Bill,
        on_delete=models.CASCADE,
        related_name="edit_history",
        verbose_name=_("bill"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("edited by"),
    )
    field_name = models.CharField(
        max_length=100,
        verbose_name=_("field name"),
    )
    old_value = models.TextField(
        blank=True,
        default="",
        verbose_name=_("old value"),
    )
    new_value = models.TextField(
        blank=True,
        default="",
        verbose_name=_("new value"),
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("timestamp"),
    )

    class Meta:
        verbose_name = _("bill edit history")
        verbose_name_plural = _("bill edit histories")
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        user_str = self.user.username if self.user else "System"
        return f"{self.field_name} modified by {user_str} at {self.timestamp}"
