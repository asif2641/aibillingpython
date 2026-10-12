"""
categories/apps.py
===============
Django app configuration for the categories app.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CategoriesConfig(AppConfig):
    """Bill categories (Grocery, Medical, Utilities, etc.)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "categories"
    verbose_name = _("Categories")
