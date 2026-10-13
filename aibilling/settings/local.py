"""
aibilling/settings/local.py
=============================
Development-only settings.

These settings override base.py for local development.
Never use this file on a production server.

Usage:
    The manage.py file points to this module by default.
    You can also set:  DJANGO_SETTINGS_MODULE=aibilling.settings.local
"""

from .base import *  # noqa: F401, F403
from .base import BASE_DIR

# ──────────────────────────────────────────────────────────────────────────────
# Development overrides
# ──────────────────────────────────────────────────────────────────────────────

# Enable debug mode (shows detailed error pages with stack traces).
# NEVER set this to True on a production server — it leaks source code.
DEBUG = True  # noqa: F811

# Allow requests from the local development server.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]  # noqa: F811, S104

# Use SQLite for local development — it's a single file, no setup needed.
DATABASES = {  # noqa: F811
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # type: ignore[name-defined]
    }
}

# Disable WhiteNoise's compressed/hashed static files in development
# so that changes to static files are reflected immediately.
STORAGES = {  # noqa: F811
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Django Debug Toolbar (optional — install separately if needed)
# INSTALLED_APPS += ["debug_toolbar"]
# MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE
# INTERNAL_IPS = ["127.0.0.1"]
