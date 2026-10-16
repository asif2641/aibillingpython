"""
aibilling/urls.py
==================
Root URL configuration for the aibilling project.

URL patterns are wrapped in i18n_patterns() so each language gets its own
URL prefix (e.g., /en/dashboard/, /ur/dashboard/).

The language switcher at set_language lets users switch language without
losing their current page.
"""

from django.conf import settings

# Language-prefixed URLs (e.g., /en/admin/, /ur/admin/)
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path, re_path
from django.views.i18n import set_language
from django.views.static import serve

from aibilling.views import (
    dashboard_view,
    global_search_view,
    healthcheck_view,
    landing_page_view,
    manifest_view,
    offline_view,
    service_worker_view,
)

urlpatterns = [
    # Healthcheck endpoint for cloud load balancers & monitoring (outside i18n)
    path("healthz/", healthcheck_view, name="healthcheck"),
    # Static files serving route
    re_path(r"^static/(?P<path>.*)$", serve, {"document_root": settings.STATICFILES_DIRS[0]}),
    # Media files serving route
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    # PWA Service Worker & Web App Manifest (served at root, outside i18n)
    path("sw.js", service_worker_view, name="service_worker"),
    path("manifest.json", manifest_view, name="manifest"),
    path("offline/", offline_view, name="offline"),
    # Language switcher — must be outside i18n_patterns.
    # POST to this URL with a "language" form field to change the active language.
    path("i18n/set-language/", set_language, name="set_language"),
    # Non-prefixed API endpoints for offline PWA sync (/sync/push/, /sync/pull/, /sync/status/)
    path("sync/", include("sync.urls", namespace="sync_root")),
]

urlpatterns += i18n_patterns(
    # Public SaaS Landing page at root of localized paths (/en/, /ur/)
    path("", landing_page_view, name="landing"),
    # Main dashboard view for authenticated users (/en/dashboard/, /ur/dashboard/)
    path("dashboard/", dashboard_view, name="dashboard"),
    # Global search across bills, parties, and items
    path("search/", global_search_view, name="global_search"),
    # Offline fallback shell for localized paths (/en/offline/, /ur/offline/)
    path("offline/", offline_view, name="offline_localized"),
    # Django admin panel.
    path("admin/", admin.site.urls),
    # Accounts app (login, logout, password change, etc.)
    path("accounts/", include("accounts.urls", namespace="accounts")),
    # Settings app (shop profile, staff management, units/categories under settings)
    path("settings/", include("settings_app.urls")),
    # Categories & units app
    path("categories/", include("categories.urls", namespace="categories")),
    # Parties app (vendors and customers)
    path("parties/", include("parties.urls", namespace="parties")),
    # Bills app (invoices, line items, trash)
    path("bills/", include("bills.urls", namespace="bills")),
    # Scanning app (AI document upload and split-screen review)
    path("scanning/", include("scanning.urls", namespace="scanning")),
    # Ledger app (payments and balances)
    path("ledger/", include("ledger.urls", namespace="ledger")),
    # Reports app (spending analytics, price history, CSV exports)
    path("reports/", include("reports.urls", namespace="reports")),
    # Sync app (offline PWA sync endpoints)
    path("sync/", include("sync.urls", namespace="sync")),
    # Prefix URLs with the language code (default: True).
    prefix_default_language=True,
)

# Serve uploaded media files and static assets in development.
# In production, WhiteNoise or a CDN handles this.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()
