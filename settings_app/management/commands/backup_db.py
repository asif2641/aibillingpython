"""
settings_app/management/commands/backup_db.py
=============================================
Management command to export a JSON database backup with retention pruning.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from settings_app.services import create_database_backup


class Command(BaseCommand):
    """Create a timestamped JSON database backup and prune expired backups."""

    help = "Create a JSON database backup and remove backups older than retention days."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--output-dir",
            type=str,
            default=str(settings.BASE_DIR / "backups"),
            help="Directory to write backup JSON files into.",
        )
        parser.add_argument(
            "--retention-days",
            type=int,
            default=30,
            help="Number of days to retain existing backup_*.json files (default: 30).",
        )

    def handle(self, *args, **options) -> None:
        output_dir = options["output_dir"]
        retention_days = options["retention_days"]

        backup_path = create_database_backup(
            output_dir=output_dir,
            retention_days=retention_days,
            user=None,
        )

        self.stdout.write(self.style.SUCCESS(f"Database backup created at {backup_path}"))
