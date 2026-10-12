"""
aibilling/settings/__init__.py
================================
This package provides environment-specific Django settings.

Import from base.py by default so that running `manage.py` commands
without specifying a settings module still works in development.
"""

from .base import *  # noqa: F401, F403
