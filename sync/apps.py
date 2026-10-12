"""
sync/apps.py
===============
Django app configuration for the sync app.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SyncConfig(AppConfig):
    """Offline sync queue for PWA (stub for Phase 6)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "sync"
    verbose_name = _("Sync")
