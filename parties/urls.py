"""parties/urls.py
================
URL patterns for the parties app.
"""

from django.urls import path

from parties.views import (
    customer_list_view,
    party_add_view,
    party_edit_view,
    vendor_list_view,
)

app_name = "parties"

urlpatterns = [
    path("vendors/", vendor_list_view, name="vendor_list"),
    path("customers/", customer_list_view, name="customer_list"),
    path("add/", party_add_view, name="party_add"),
    path("<int:pk>/edit/", party_edit_view, name="party_edit"),
]
