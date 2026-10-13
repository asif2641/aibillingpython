"""
sync/urls.py
============
URL routing configuration for the sync app.
"""

from django.urls import path

from sync.views import sync_pull_view, sync_push_view, sync_status_view

app_name = "sync"

urlpatterns = [
    path("push/", sync_push_view, name="push"),
    path("pull/", sync_pull_view, name="pull"),
    path("status/", sync_status_view, name="status"),
]
