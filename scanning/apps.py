"""
scanning/apps.py
===============
Django app configuration for the scanning app.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ScanningConfig(AppConfig):
    """AI-powered bill scanning and extraction (stub for Phase 4)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "scanning"
    verbose_name = _("Scanning")
