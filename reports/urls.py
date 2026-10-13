"""reports/urls.py
===============
URL configuration for the reports and analytics app.
"""

from django.urls import path

from reports.views import (
    export_spending_csv_view,
    price_history_view,
    spending_report_view,
)

app_name = "reports"

urlpatterns = [
    path("spending/", spending_report_view, name="spending_report"),
    path("spending/export/csv/", export_spending_csv_view, name="spending_csv"),
    path("price-history/", price_history_view, name="price_history"),
]
