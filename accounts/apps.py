"""
accounts/apps.py
=================
Django app configuration for the accounts app.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    """Configuration for the accounts app (custom User model and auth flows)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = _("Accounts")
