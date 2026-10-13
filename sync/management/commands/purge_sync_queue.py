"""
sync/management/commands/purge_sync_queue.py
============================================
Management command to purge old processed (and optionally failed) sync queue records.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from settings_app.services import log_activity
from sync.models import SyncQueue


class Command(BaseCommand):
    """Purge old processed (and optionally failed) SyncQueue records."""

    help = "Purge processed (and optionally failed) SyncQueue items older than N days."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Purge records older than this many days (default: 30).",
        )
        parser.add_argument(
            "--include-failed",
            action="store_true",
            default=False,
            help="Also purge failed sync queue records older than the cutoff.",
        )

    def handle(self, *args, **options) -> None:
        days: int = options["days"]
        include_failed: bool = options["include_failed"]

        cutoff = timezone.now() - timedelta(days=days)
        statuses = [SyncQueue.Status.PROCESSED]
        if include_failed:
            statuses.append(SyncQueue.Status.FAILED)

        qs = SyncQueue.objects.filter(status__in=statuses).filter(
            Q(processed_at__lt=cutoff) | Q(server_timestamp__lt=cutoff)
        )
        deleted_count, _ = qs.delete()

        log_activity(
            user=None,
            action="sync_purged",
            target_type="System",
            description=f"Purged {deleted_count} sync queue records older than {days} days.",
            metadata={
                "deleted_count": deleted_count,
                "days": days,
                "include_failed": include_failed,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Purged {deleted_count} processed sync queue records older than {days} days."
            )
        )
