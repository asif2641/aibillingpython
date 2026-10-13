"""
sync/models.py
==============
Models for the offline synchronization queue (PWA sync).
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class SyncQueue(models.Model):
    """Offline synchronization queue item for PWA client sync."""

    class RecordType(models.TextChoices):
        BILL = "bill", _("Bill")
        PARTY = "party", _("Party")
        PAYMENT = "payment", _("Payment")

    class Action(models.TextChoices):
        CREATE = "create", _("Create")
        UPDATE = "update", _("Update")
        DELETE = "delete", _("Delete")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PROCESSED = "processed", _("Processed")
        FAILED = "failed", _("Failed")
        CONFLICT = "conflict", _("Conflict")

    client_id = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name=_("client ID"),
        help_text=_("Client-generated UUID for idempotency."),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sync_items",
        verbose_name=_("user"),
    )
    record_type = models.CharField(
        max_length=50,
        choices=RecordType.choices,
        default=RecordType.BILL,
        verbose_name=_("record type"),
    )
    action = models.CharField(
        max_length=20,
        choices=Action.choices,
        default=Action.CREATE,
        verbose_name=_("action"),
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("payload"),
        help_text=_("Serialized offline data."),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name=_("status"),
    )
    client_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("client timestamp"),
    )
    server_timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("server timestamp"),
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("processed at"),
    )
    error_message = models.TextField(
        blank=True,
        default="",
        verbose_name=_("error message"),
    )
    resolved_record_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("resolved record ID"),
    )
    retry_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("retry count"),
    )

    class Meta:
        verbose_name = _("sync queue item")
        verbose_name_plural = _("sync queue items")
        ordering = ["server_timestamp"]
        indexes = [
            models.Index(fields=["status", "server_timestamp"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:
        return f"SyncQueue({self.client_id}, {self.record_type}, {self.status})"

    @property
    def created_at(self):
        """Alias for server_timestamp to maintain timestamp convention."""
        return self.server_timestamp

    @property
    def updated_at(self):
        """Alias for processed_at or server_timestamp."""
        return self.processed_at or self.server_timestamp
