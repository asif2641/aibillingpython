"""scanning/urls.py
================
URL routing for scanning app.
"""

from django.urls import path

from scanning.views import review_view, upload_view

app_name = "scanning"

urlpatterns = [
    path("upload/", upload_view, name="upload"),
    path("review/<int:job_id>/", review_view, name="review"),
]
