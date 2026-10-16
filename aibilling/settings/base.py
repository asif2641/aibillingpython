"""
aibilling/settings/base.py
============================
Shared Django settings used by all environments (local, production, CI).

Environment-specific settings (DEBUG, database, etc.) are set in
local.py or production.py, which import from this file.

All secrets are loaded from a .env file via python-dotenv.
Never hard-code secrets here.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────

# BASE_DIR points to the root of the project (where manage.py lives).
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from a .env file in the project root.
# This means you can keep secrets in .env without hard-coding them here.
load_dotenv(BASE_DIR / ".env")


# ──────────────────────────────────────────────────────────────────────────────
# Security
# ──────────────────────────────────────────────────────────────────────────────

# SECURITY WARNING: keep the secret key used in production secret!
# The fallback value is only used in development. Production MUST set SECRET_KEY in .env.
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key-change-in-production")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DEBUG", "True") == "True"

# Hosts that are allowed to serve the app. Overridden in production.
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

# Security headers enforced across all environments
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"


# ──────────────────────────────────────────────────────────────────────────────
# Application definition
# ──────────────────────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    # Django built-ins
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Project apps
    "accounts",
    "bills",
    "parties",
    "ledger",
    "reports",
    "scanning",
    "categories",
    "settings_app",
    "sync",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves static files efficiently without a separate web server.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # LocaleMiddleware must be after SessionMiddleware and before CommonMiddleware.
    # It detects the user's language preference from the URL, session, or browser.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "aibilling.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Look for templates in a top-level templates/ directory.
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Makes the current language available in every template.
                "django.template.context_processors.i18n",
            ],
        },
    },
]

WSGI_APPLICATION = "aibilling.wsgi.application"


# ──────────────────────────────────────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────────────────────────────────────


def parse_database_url(url: str) -> dict:
    """Parse a PostgreSQL DATABASE_URL string into a Django DATABASES dictionary."""
    import urllib.parse

    parsed = urllib.parse.urlparse(url)
    query_params = dict(urllib.parse.parse_qsl(parsed.query))
    db_config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": urllib.parse.unquote(parsed.path.lstrip("/")),
        "USER": urllib.parse.unquote(parsed.username or ""),
        "PASSWORD": urllib.parse.unquote(parsed.password or ""),
        "HOST": parsed.hostname or "localhost",
        "PORT": parsed.port or 5432,
        "CONN_MAX_AGE": int(os.environ.get("CONN_MAX_AGE", "60")),
    }
    if query_params:
        db_config["OPTIONS"] = query_params
    return db_config


# Reads the DATABASE_URL environment variable.
# If not set, falls back to SQLite (a local file — perfect for development).
_database_url = os.environ.get("DATABASE_URL", "")

if _database_url.startswith(("postgres://", "postgresql://")):
    DATABASES = {"default": parse_database_url(_database_url)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# ──────────────────────────────────────────────────────────────────────────────
# Custom user model
# ──────────────────────────────────────────────────────────────────────────────

# Tell Django to use our custom User model from the accounts app.
AUTH_USER_MODEL = "accounts.User"

# Where to redirect users after login and after logout.
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "accounts:login"


# ──────────────────────────────────────────────────────────────────────────────
# Password validation
# ──────────────────────────────────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Internationalization (i18n)
# ──────────────────────────────────────────────────────────────────────────────

# Enable Django's translation system.
USE_I18N = True

# Primary language for the app.
LANGUAGE_CODE = "en"

# Languages available in the language switcher.
LANGUAGES = [
    ("en", "English"),
    ("ur", "Urdu"),
]

# Django will look for translation files (.po / .mo) in these directories.
LOCALE_PATHS = [BASE_DIR / "locale"]

# Store all dates and times in UTC in the database.
# Always convert to the user's local time zone when displaying.
USE_TZ = True
TIME_ZONE = "UTC"


# ──────────────────────────────────────────────────────────────────────────────
# Static, media, and backup files
# ──────────────────────────────────────────────────────────────────────────────

STATIC_URL = "/static/"
# Additional directories where Django looks for static files.
STATICFILES_DIRS = [BASE_DIR / "static"]
# Where `collectstatic` places all files (used in production).
STATIC_ROOT = BASE_DIR / "staticfiles"

# Django 4.2+ STORAGES setting: WhiteNoise serves compressed static files.
# On Vercel serverless, use CompressedStaticFilesStorage without manifest hashing
# so Vercel's edge CDN serves static assets directly without hash mismatches.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedStaticFilesStorage"
            if bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_URL"))
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}
# Prevent missing manifest entries from raising 500 errors in serverless environments
WHITENOISE_MANIFEST_STRICT = False


MEDIA_URL = "/media/"
# Uploaded files (bill images, shop logos, etc.) are stored here.
# On Vercel / AWS Lambda serverless functions, the root filesystem is read-only.
is_read_only_fs = bool(
    os.environ.get("VERCEL")
    or os.environ.get("VERCEL_URL")
    or os.environ.get("VERCEL_ENV")
    or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    or os.environ.get("LAMBDA_TASK_ROOT")
) or not os.access(str(BASE_DIR), os.W_OK)
if is_read_only_fs:
    import tempfile

    MEDIA_ROOT = Path(tempfile.gettempdir()) / "media"
    BACKUP_DIR = Path(tempfile.gettempdir()) / "backups"
else:
    MEDIA_ROOT = BASE_DIR / "media"
    BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", BASE_DIR / "backups"))

try:
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
except Exception:  # noqa: S110
    pass


# ──────────────────────────────────────────────────────────────────────────────
# AI provider settings (read from .env — never hard-code API keys)
# ──────────────────────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
AI_PROVIDER = os.environ.get("AI_PROVIDER", "gemini")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Scan rate limits — protect against runaway API costs.
DAILY_SCAN_LIMIT = int(os.environ.get("DAILY_SCAN_LIMIT", "50"))
MONTHLY_SCAN_LIMIT = int(os.environ.get("MONTHLY_SCAN_LIMIT", "500"))


# ──────────────────────────────────────────────────────────────────────────────
# Default auto-field
# ──────────────────────────────────────────────────────────────────────────────

# Use BigAutoField (64-bit integer primary key) for all new models.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
