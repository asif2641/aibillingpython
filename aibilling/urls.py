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
from django.urls import include, path
from django.views.i18n import set_language

from aibilling.views import dashboard_view

urlpatterns = [
    # Language switcher — must be outside i18n_patterns.
    # POST to this URL with a "language" form field to change the active language.
    path("i18n/set-language/", set_language, name="set_language"),
]

urlpatterns += i18n_patterns(
    # Main dashboard view at root of localized paths (/en/, /ur/)
    path("", dashboard_view, name="dashboard"),
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
    # Prefix URLs with the language code (default: True).
    prefix_default_language=True,
)

# Serve uploaded media files in development.
# In production, a CDN or cloud storage handles this.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
