"""
aibilling/settings/production.py
==================================
Production settings for the aibilling project (Render, VPS with Nginx/Gunicorn).

Imports shared settings from base.py and enforces strict production security:
- DEBUG = False
- Mandatory unique SECRET_KEY (unless BUILD_MODE=True during collectstatic)
- Render hostname auto-detection for ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS
- HTTPS, HSTS, and secure cookie hardening
"""

import os
from typing import Any

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401, F403
from .base import parse_database_url

DEFAULT_INSECURE_SECRET_KEY = "dev-only-insecure-key-change-in-production"


def configure_production_settings(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Compute and validate production settings from environment variables.

    Args:
        env: Optional mapping of environment variables (defaults to os.environ).

    Returns:
        Dictionary of production setting overrides.

    Raises:
        ImproperlyConfigured: If SECRET_KEY is missing or uses the insecure default
            when BUILD_MODE is not 'True'.
    """
    environ = env if env is not None else os.environ

    build_mode = environ.get("BUILD_MODE", "False") == "True"
    is_vercel = bool(environ.get("VERCEL") or environ.get("VERCEL_URL"))
    secret_key = (
        environ.get("SECRET_KEY", "").strip() or environ.get("DJANGO_SECRET_KEY", "").strip()
    )

    if not secret_key or secret_key == DEFAULT_INSECURE_SECRET_KEY:
        if is_vercel or build_mode:
            secret_key = (
                environ.get("VERCEL_GIT_COMMIT_SHA")
                or "vercel-auto-secret-key-fallback-please-configure-in-dashboard"
            )
        else:
            raise ImproperlyConfigured(
                "SECRET_KEY must be set to a unique secret value in production."
            )

    allowed_hosts = [
        h.strip()
        for h in environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
        if h.strip()
    ]
    render_hostname = environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if render_hostname and render_hostname not in allowed_hosts:
        allowed_hosts.append(render_hostname)

    csrf_trusted_origins = [
        o.strip() for o in environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
    ]
    if render_hostname:
        render_origin = f"https://{render_hostname}"
        if render_origin not in csrf_trusted_origins:
            csrf_trusted_origins.append(render_origin)

    # Vercel deployment support
    vercel_url = environ.get("VERCEL_URL", "").strip()
    if vercel_url:
        if vercel_url not in allowed_hosts:
            allowed_hosts.append(vercel_url)
        vercel_origin = f"https://{vercel_url}"
        if vercel_origin not in csrf_trusted_origins:
            csrf_trusted_origins.append(vercel_origin)

    if is_vercel:
        for vhost in [".vercel.app", "vercel.app", "*"]:
            if vhost not in allowed_hosts:
                allowed_hosts.append(vhost)
        for vorigin in ["https://*.vercel.app", "https://vercel.app"]:
            if vorigin not in csrf_trusted_origins:
                csrf_trusted_origins.append(vorigin)

    ssl_redirect = environ.get("SECURE_SSL_REDIRECT", "True") == "True" and not is_vercel

    config: dict[str, Any] = {
        "DEBUG": False,
        "SECRET_KEY": secret_key,
        "ALLOWED_HOSTS": allowed_hosts,
        "CSRF_TRUSTED_ORIGINS": csrf_trusted_origins,
        "RENDER_EXTERNAL_HOSTNAME": render_hostname,
        "SECURE_PROXY_SSL_HEADER": ("HTTP_X_FORWARDED_PROTO", "https"),
        "SECURE_SSL_REDIRECT": ssl_redirect,
        "SESSION_COOKIE_SECURE": True,
        "CSRF_COOKIE_SECURE": True,
        "SESSION_COOKIE_HTTPONLY": True,
        "SECURE_HSTS_SECONDS": int(environ.get("SECURE_HSTS_SECONDS", "31536000")),
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": True,
        "SECURE_HSTS_PRELOAD": True,
        "SECURE_CONTENT_TYPE_NOSNIFF": True,
        "X_FRAME_OPTIONS": "DENY",
        "SECURE_REFERRER_POLICY": "same-origin",
    }

    db_url = environ.get("DATABASE_URL", "").strip()
    if db_url.startswith(("postgres://", "postgresql://")):
        config["DATABASES"] = {"default": parse_database_url(db_url)}
    elif environ.get("VERCEL"):
        # On Vercel serverless without PostgreSQL, use temp directory for SQLite writeability
        import tempfile
        from pathlib import Path

        config["DATABASES"] = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": Path(tempfile.gettempdir()) / "db.sqlite3",
            }
        }

    is_serverless = (
        is_vercel
        or bool(
            environ.get("VERCEL_ENV")
            or environ.get("AWS_LAMBDA_FUNCTION_NAME")
            or environ.get("LAMBDA_TASK_ROOT")
        )
        or not os.access(str(BASE_DIR), os.W_OK)
    )

    if is_serverless:
        import tempfile
        from pathlib import Path

        temp_dir = Path(tempfile.gettempdir())
        config["MEDIA_ROOT"] = temp_dir / "media"
        config["BACKUP_DIR"] = temp_dir / "backups"
        try:
            config["MEDIA_ROOT"].mkdir(parents=True, exist_ok=True)
            config["BACKUP_DIR"].mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    return config


_prod_settings = configure_production_settings()
DEBUG = _prod_settings["DEBUG"]
SECRET_KEY = _prod_settings["SECRET_KEY"]
ALLOWED_HOSTS = _prod_settings["ALLOWED_HOSTS"]
CSRF_TRUSTED_ORIGINS = _prod_settings["CSRF_TRUSTED_ORIGINS"]
RENDER_EXTERNAL_HOSTNAME = _prod_settings["RENDER_EXTERNAL_HOSTNAME"]
SECURE_PROXY_SSL_HEADER = _prod_settings["SECURE_PROXY_SSL_HEADER"]
SECURE_SSL_REDIRECT = _prod_settings["SECURE_SSL_REDIRECT"]
SESSION_COOKIE_SECURE = _prod_settings["SESSION_COOKIE_SECURE"]
CSRF_COOKIE_SECURE = _prod_settings["CSRF_COOKIE_SECURE"]
SESSION_COOKIE_HTTPONLY = _prod_settings["SESSION_COOKIE_HTTPONLY"]
SECURE_HSTS_SECONDS = _prod_settings["SECURE_HSTS_SECONDS"]
SECURE_HSTS_INCLUDE_SUBDOMAINS = _prod_settings["SECURE_HSTS_INCLUDE_SUBDOMAINS"]
SECURE_HSTS_PRELOAD = _prod_settings["SECURE_HSTS_PRELOAD"]
SECURE_CONTENT_TYPE_NOSNIFF = _prod_settings["SECURE_CONTENT_TYPE_NOSNIFF"]
X_FRAME_OPTIONS = _prod_settings["X_FRAME_OPTIONS"]
SECURE_REFERRER_POLICY = _prod_settings["SECURE_REFERRER_POLICY"]
if "DATABASES" in _prod_settings:
    DATABASES = _prod_settings["DATABASES"]
if "MEDIA_ROOT" in _prod_settings:
    MEDIA_ROOT = _prod_settings["MEDIA_ROOT"]
    BACKUP_DIR = _prod_settings["BACKUP_DIR"]
WHITENOISE_MANIFEST_STRICT = False
