"""
settings_app/apps.py
===============
Django app configuration for the settings_app app.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SettingsConfig(AppConfig):
    """Shop profile, staff permissions, and application settings."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "settings_app"
    verbose_name = _("Settings")
