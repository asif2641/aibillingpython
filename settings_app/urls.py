"""
settings_app/urls.py
====================
URL routing for Shop Profile, Staff Management, Activity Log, Backups, and Settings.
"""

from django.urls import path

from accounts import views as accounts_views
from categories import views as categories_views
from settings_app import views

urlpatterns = [
    # Shop profile
    path("shop/", views.shop_profile_view, name="shop_profile"),
    # Staff management
    path("staff/", accounts_views.staff_list_view, name="staff_list"),
    path("staff/add/", accounts_views.staff_add_view, name="staff_add"),
    path(
        "staff/<int:user_id>/toggle-status/",
        accounts_views.staff_toggle_status_view,
        name="staff_toggle_status",
    ),
    path(
        "staff/<int:user_id>/permissions/",
        accounts_views.staff_permissions_view,
        name="staff_permissions",
    ),
    path(
        "staff/<int:user_id>/reset-password/",
        accounts_views.staff_reset_password_view,
        name="staff_reset_password",
    ),
    # Activity Log & Backups
    path("activity-log/", views.activity_log_view, name="activity_log"),
    path("backups/", views.backup_export_view, name="backup_export"),
    path("backups/create/", views.backup_create_view, name="backup_create"),
    path("backups/download-json/", views.backup_download_json_view, name="backup_download_json"),
    path("backups/download-csv/", views.backup_download_csv_view, name="backup_download_csv"),
    # Category and Unit aliases under settings
    path("categories/", categories_views.category_list_view),
    path("categories/add/", categories_views.category_add_view),
    path("categories/<int:pk>/edit/", categories_views.category_edit_view),
    path("categories/<int:pk>/archive/", categories_views.category_archive_view),
    path("units/", categories_views.unit_list_view),
    path("units/add/", categories_views.unit_add_view),
]
