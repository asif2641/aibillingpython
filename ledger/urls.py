"""ledger/urls.py
==============
URL configuration for the ledger app.
"""

from django.urls import path

from ledger.views import (
    ledger_dashboard_view,
    party_ledger_csv_view,
    party_ledger_view,
    payment_add_view,
)

app_name = "ledger"

urlpatterns = [
    path("", ledger_dashboard_view, name="ledger_dashboard"),
    path("payments/add/", payment_add_view, name="payment_add"),
    path("party/<int:party_id>/", party_ledger_view, name="party_ledger"),
    path("party/<int:party_id>/export/csv/", party_ledger_csv_view, name="party_ledger_csv"),
]
