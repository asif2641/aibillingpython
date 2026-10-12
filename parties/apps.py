"""
parties/apps.py
===============
Django app configuration for the parties app.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PartiesConfig(AppConfig):
    """Manages vendor and customer profiles (collectively called parties)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "parties"
    verbose_name = _("Parties")
