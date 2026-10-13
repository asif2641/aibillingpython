"""reports/urls.py
===============
URL configuration for the reports and analytics app.
"""

from django.urls import path

from reports.views import (
    export_incorrect_bills_csv_view,
    export_spending_csv_view,
    incorrect_bills_report_view,
    price_history_view,
    spending_report_view,
)

app_name = "reports"

urlpatterns = [
    path("spending/", spending_report_view, name="spending_report"),
    path("spending/export/csv/", export_spending_csv_view, name="spending_csv"),
    path("price-history/", price_history_view, name="price_history"),
    path("incorrect-bills/", incorrect_bills_report_view, name="incorrect_bills"),
    path(
        "incorrect-bills/export/csv/",
        export_incorrect_bills_csv_view,
        name="incorrect_bills_csv",
    ),
]
