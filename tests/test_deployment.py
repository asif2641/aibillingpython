"""
tests/test_deployment.py
=========================
Phase 8 test suite verifying:
1. Healthcheck endpoint (/healthz/)
2. Database URL parsing (parse_database_url in aibilling.settings.base)
3. Production settings security & Render/VPS auto-configuration (aibilling.settings.production)
4. Static files & Django 5.1 STORAGES configuration + collectstatic
5. Deployment artifacts (build.sh, Procfile, render.yaml, deploy/*, docs/DEPLOYMENT.md)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import Client

import aibilling.settings.base as base_settings

BASE_DIR = Path(settings.BASE_DIR)


def _reload_production_settings():
    """Reload base and production settings modules to pick up current os.environ."""
    importlib.reload(base_settings)
    if "aibilling.settings.production" in sys.modules:
        return importlib.reload(sys.modules["aibilling.settings.production"])
    return importlib.import_module("aibilling.settings.production")


# ──────────────────────────────────────────────────────────────────────────────
# 1. Healthcheck Endpoint (/healthz/)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestHealthcheckEndpoint:
    """Verify the unauthenticated /healthz/ endpoint used by Render, Docker, and Nginx."""

    def test_healthz_returns_200_without_auth_or_i18n_redirect(self):
        """GET /healthz/ must return 200 directly without redirecting to /en/ or login."""
        client = Client()
        response = client.get("/healthz/")
        assert response.status_code == 200
        assert response["Content-Type"].startswith("application/json")

    def test_healthz_json_payload_reports_db_connected(self):
        """GET /healthz/ returns JSON {"status": "ok", "database": "connected"}."""
        client = Client()
        response = client.get("/healthz/")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert data.get("database") == "connected"

    def test_healthz_post_method_not_allowed(self):
        """POST /healthz/ returns HTTP 405 Method Not Allowed."""
        client = Client()
        response = client.post("/healthz/")
        assert response.status_code == 405


# ──────────────────────────────────────────────────────────────────────────────
# 2. Database URL Parsing (parse_database_url in aibilling.settings.base)
# ──────────────────────────────────────────────────────────────────────────────


class TestDatabaseUrlParsing:
    """Verify PostgreSQL connection string parsing in aibilling.settings.base."""

    def test_parse_standard_postgresql_url(self):
        """Standard postgresql:// URL parses ENGINE, NAME, USER, PASSWORD, HOST, PORT."""
        assert hasattr(
            base_settings, "parse_database_url"
        ), "aibilling.settings.base must define parse_database_url(url)"
        cfg = base_settings.parse_database_url(
            "postgresql://billing_user:s3cretPass@db.example.com:5432/aibilling_prod"
        )
        assert cfg["ENGINE"] == "django.db.backends.postgresql"
        assert cfg["NAME"] == "aibilling_prod"
        assert cfg["USER"] == "billing_user"
        assert cfg["PASSWORD"] == "s3cretPass"
        assert cfg["HOST"] == "db.example.com"
        assert int(cfg["PORT"]) == 5432

    def test_parse_postgres_scheme_alias_and_default_port(self):
        """postgres:// alias works and defaults PORT to 5432 when omitted."""
        assert hasattr(base_settings, "parse_database_url")
        cfg = base_settings.parse_database_url(
            "postgres://neondb_owner:pass123@ep-cool.aws.neon.tech/neondb"
        )
        assert cfg["ENGINE"] == "django.db.backends.postgresql"
        assert cfg["NAME"] == "neondb"
        assert cfg["USER"] == "neondb_owner"
        assert cfg["PASSWORD"] == "pass123"
        assert cfg["HOST"] == "ep-cool.aws.neon.tech"
        assert int(cfg["PORT"]) == 5432

    def test_parse_database_url_query_options_sslmode(self):
        """Query parameters like ?sslmode=require are parsed into OPTIONS dict."""
        assert hasattr(base_settings, "parse_database_url")
        cfg = base_settings.parse_database_url(
            "postgresql://user:pass@ep-xyz.us-east-2.aws.neon.tech:5432/neondb?sslmode=require"
        )
        assert "OPTIONS" in cfg
        assert cfg["OPTIONS"].get("sslmode") == "require"

    def test_sqlite_fallback_when_database_url_empty(self, monkeypatch):
        """When DATABASE_URL is empty, base.py configures SQLite3 by default."""
        monkeypatch.setenv("DATABASE_URL", "")
        importlib.reload(base_settings)
        assert base_settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"


# ──────────────────────────────────────────────────────────────────────────────
# 3. Production Settings (aibilling/settings/production.py)
# ──────────────────────────────────────────────────────────────────────────────


class TestProductionSettings:
    """Verify security enforcement and environment configuration in production.py."""

    def test_production_rejects_default_insecure_secret_key(self, monkeypatch):
        """Loading production settings with the default insecure SECRET_KEY raises ImproperlyConfigured."""
        monkeypatch.setenv("SECRET_KEY", "dev-only-insecure-key-change-in-production")
        monkeypatch.delenv("BUILD_MODE", raising=False)

        with pytest.raises(ImproperlyConfigured):
            _reload_production_settings()

    def test_production_allows_build_mode_without_custom_secret_key(self, monkeypatch):
        """BUILD_MODE=True allows loading production settings during CI/Render build (collectstatic)."""
        monkeypatch.setenv("SECRET_KEY", "dev-only-insecure-key-change-in-production")
        monkeypatch.setenv("BUILD_MODE", "True")

        prod = _reload_production_settings()
        assert prod.DEBUG is False

    def test_production_render_hostname_and_allowed_hosts(self, monkeypatch):
        """RENDER_EXTERNAL_HOSTNAME is automatically added to ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS."""
        monkeypatch.setenv("SECRET_KEY", "prod-strong-secret-key-9876543210-abcdef")
        monkeypatch.delenv("BUILD_MODE", raising=False)
        monkeypatch.setenv("ALLOWED_HOSTS", "billing.example.com")
        monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "my-billing-app.onrender.com")
        monkeypatch.setenv("CSRF_TRUSTED_ORIGINS", "https://billing.example.com")

        prod = _reload_production_settings()
        assert prod.DEBUG is False
        assert "my-billing-app.onrender.com" in prod.ALLOWED_HOSTS
        assert "billing.example.com" in prod.ALLOWED_HOSTS
        assert "https://my-billing-app.onrender.com" in prod.CSRF_TRUSTED_ORIGINS
        assert "https://billing.example.com" in prod.CSRF_TRUSTED_ORIGINS

    def test_production_cookie_and_hsts_security_headers(self, monkeypatch):
        """Production settings enforce secure cookies, HSTS (1 year+), and reverse proxy SSL headers."""
        monkeypatch.setenv("SECRET_KEY", "prod-strong-secret-key-9876543210-abcdef")
        monkeypatch.delenv("BUILD_MODE", raising=False)
        monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "my-billing-app.onrender.com")

        prod = _reload_production_settings()
        assert prod.SESSION_COOKIE_SECURE is True
        assert prod.CSRF_COOKIE_SECURE is True
        assert prod.SESSION_COOKIE_HTTPONLY is True
        assert prod.SECURE_HSTS_SECONDS >= 31536000
        assert prod.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
        assert prod.SECURE_HSTS_PRELOAD is True
        assert prod.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")


# ──────────────────────────────────────────────────────────────────────────────
# 4. Static Files & STORAGES Configuration
# ──────────────────────────────────────────────────────────────────────────────


class TestStaticFilesConfiguration:
    """Verify Django 5.1 STORAGES dictionary and collectstatic execution."""

    def test_storages_uses_whitenoise_and_removes_legacy_setting(self):
        """base.py defines STORAGES['staticfiles'] with WhiteNoise and omits legacy STATICFILES_STORAGE."""
        importlib.reload(base_settings)
        assert hasattr(
            base_settings, "STORAGES"
        ), "STORAGES must be defined in aibilling.settings.base"
        assert "staticfiles" in base_settings.STORAGES
        assert "default" in base_settings.STORAGES
        backend = base_settings.STORAGES["staticfiles"]["BACKEND"]
        assert backend in (
            "whitenoise.storage.CompressedStaticFilesStorage",
            "whitenoise.storage.CompressedManifestStaticFilesStorage",
        )
        assert not hasattr(
            base_settings, "STATICFILES_STORAGE"
        ), "Remove deprecated STATICFILES_STORAGE in favor of STORAGES"

    def test_collectstatic_dry_run_succeeds(self):
        """Running collectstatic --dry-run --noinput completes without errors."""
        call_command("collectstatic", interactive=False, dry_run=True, verbosity=0)


# ──────────────────────────────────────────────────────────────────────────────
# 5. Deployment Artifacts & Documentation Verification
# ──────────────────────────────────────────────────────────────────────────────


class TestDeploymentArtifacts:
    """Verify all required deployment configuration files and documentation exist and are complete."""

    def test_build_sh_exists_and_runs_install_collectstatic_migrate(self):
        """build.sh exists at project root and runs pip install, collectstatic, and migrate."""
        build_sh = BASE_DIR / "build.sh"
        assert build_sh.is_file(), "build.sh must exist at project root"
        content = build_sh.read_text(encoding="utf-8")
        assert "pip install" in content
        assert "collectstatic" in content
        assert "migrate" in content

    def test_procfile_exists_and_configures_gunicorn(self):
        """Procfile exists at project root and launches gunicorn with aibilling.wsgi:application."""
        procfile = BASE_DIR / "Procfile"
        assert procfile.is_file(), "Procfile must exist at project root"
        content = procfile.read_text(encoding="utf-8")
        assert "gunicorn" in content
        assert "aibilling.wsgi:application" in content

    def test_render_yaml_exists_and_configures_production_and_healthcheck(self):
        """render.yaml exists at project root with production settings and /healthz/ check."""
        render_yaml = BASE_DIR / "render.yaml"
        assert render_yaml.is_file(), "render.yaml must exist at project root"
        content = render_yaml.read_text(encoding="utf-8")
        assert "aibilling.settings.production" in content
        assert "/healthz/" in content

    def test_systemd_gunicorn_service_template_exists(self):
        """deploy/gunicorn.service exists and references aibilling.wsgi:application and production settings."""
        service_file = BASE_DIR / "deploy" / "gunicorn.service"
        assert service_file.is_file(), "deploy/gunicorn.service must exist"
        content = service_file.read_text(encoding="utf-8")
        assert "aibilling.wsgi:application" in content
        assert "aibilling.settings.production" in content

    def test_nginx_conf_template_exists_with_upload_limit_and_static_media(self):
        """deploy/nginx.conf exists and configures client_max_body_size, /static/, and /media/."""
        nginx_conf = BASE_DIR / "deploy" / "nginx.conf"
        assert nginx_conf.is_file(), "deploy/nginx.conf must exist"
        content = nginx_conf.read_text(encoding="utf-8")
        assert "client_max_body_size" in content
        assert "/static/" in content
        assert "/media/" in content

    def test_backup_cron_script_exists_with_backup_and_purge_commands(self):
        """deploy/backup_cron.sh exists and runs backup_db and purge_sync_queue."""
        cron_sh = BASE_DIR / "deploy" / "backup_cron.sh"
        assert cron_sh.is_file(), "deploy/backup_cron.sh must exist"
        content = cron_sh.read_text(encoding="utf-8")
        assert "backup_db" in content
        assert "purge_sync_queue" in content

    def test_deployment_documentation_covers_all_three_stages(self):
        """docs/DEPLOYMENT.md exists and documents Local, Free Server (Render), and Live VPS deployment."""
        doc_file = BASE_DIR / "docs" / "DEPLOYMENT.md"
        assert doc_file.is_file(), "docs/DEPLOYMENT.md must exist"
        content = doc_file.read_text(encoding="utf-8").lower()
        assert "local" in content
        assert "render" in content
        assert "vps" in content or "nginx" in content
        assert "gunicorn" in content

    def test_vercel_configuration_exists_with_wsgi_and_static_routes(self):
        """vercel.json and build_files.sh exist for Vercel deployment."""
        vercel_json = BASE_DIR / "vercel.json"
        assert vercel_json.is_file(), "vercel.json must exist at project root"
        content = vercel_json.read_text(encoding="utf-8")
        assert "aibilling/wsgi.py" in content
        assert "@vercel/python" in content
        assert "build_files.sh" in content

        build_files_sh = BASE_DIR / "build_files.sh"
        assert build_files_sh.is_file(), "build_files.sh must exist"
        sh_content = build_files_sh.read_text(encoding="utf-8")
        assert "collectstatic" in sh_content
