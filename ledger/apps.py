"""
ledger/apps.py
===============
Django app configuration for the ledger app.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LedgerConfig(AppConfig):
    """Records payments and maintains per-party ledger balances."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "ledger"
    verbose_name = _("Ledger")
