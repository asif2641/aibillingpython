"""scanning/urls.py
================
URL routing for scanning app.
"""

from django.urls import path

from scanning.views import check_duplicate_view, file_preview_view, review_view, upload_view

app_name = "scanning"

urlpatterns = [
    path("upload/", upload_view, name="upload"),
    path("check-duplicate/", check_duplicate_view, name="check_duplicate"),
    path("review/<int:job_id>/", review_view, name="review"),
    path("file-preview/<int:file_id>/", file_preview_view, name="file_preview"),
]
