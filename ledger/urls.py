"""ledger/urls.py
==============
URL configuration for the ledger app.
"""

from django.urls import path

from ledger.views import payment_add_view

app_name = "ledger"

urlpatterns = [
    path("payments/add/", payment_add_view, name="payment_add"),
]
