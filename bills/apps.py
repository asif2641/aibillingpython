"""
bills/apps.py
===============
Django app configuration for the bills app.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BillsConfig(AppConfig):
    """Manages bills, bill items, files, and related business logic."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "bills"
    verbose_name = _("Bills")
