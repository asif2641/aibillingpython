"""
reports/apps.py
===============
Django app configuration for the reports app.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ReportsConfig(AppConfig):
    """Generates spending reports and chart data."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "reports"
    verbose_name = _("Reports")
