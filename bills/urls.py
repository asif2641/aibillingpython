"""bills/urls.py
=============
URL routing for bills app.
"""

from django.urls import path

from bills.views import (
    bill_add_view,
    bill_correct_discrepancy_view,
    bill_delete_view,
    bill_detail_view,
    bill_edit_view,
    bill_list_view,
    bill_payment_view,
    bill_restore_view,
    bill_trash_view,
)

app_name = "bills"

urlpatterns = [
    path("", bill_list_view, name="bill_list"),
    path("add/", bill_add_view, name="bill_add"),
    path("trash/", bill_trash_view, name="bill_trash"),
    path("<int:pk>/", bill_detail_view, name="bill_detail"),
    path("<int:pk>/edit/", bill_edit_view, name="bill_edit"),
    path(
        "<int:pk>/correct-discrepancy/",
        bill_correct_discrepancy_view,
        name="bill_correct_discrepancy",
    ),
    path("<int:pk>/delete/", bill_delete_view, name="bill_delete"),
    path("<int:pk>/restore/", bill_restore_view, name="bill_restore"),
    path("<int:pk>/payment/", bill_payment_view, name="bill_payment"),
]
