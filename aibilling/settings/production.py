"""
aibilling/settings/production.py
==================================
Production settings stub.

Import from base.py and override settings that must differ in production.
This file will be completed in Phase 8 (Deployment).

Usage:
    Set this environment variable on your server:
    DJANGO_SETTINGS_MODULE=aibilling.settings.production
"""

from .base import *  # noqa: F401, F403

# ──────────────────────────────────────────────────────────────────────────────
# Production security (uncomment and configure in Phase 8)
# ──────────────────────────────────────────────────────────────────────────────

# DEBUG must be False in production. Reads from .env on the server.
# DEBUG is already set from base.py via environment variable.

# Force HTTPS. Uncomment these in Phase 8 when HTTPS is configured.
# SECURE_SSL_REDIRECT = True
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True
# SECURE_HSTS_SECONDS = 31536000  # 1 year
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD = True

# Sentry error tracking (optional — Phase 8)
# import sentry_sdk
# sentry_sdk.init(dsn=os.environ.get("SENTRY_DSN", ""), ...)
