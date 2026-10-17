"""
accounts/urls.py
=================
URL patterns for the accounts app.

All URLs are namespaced under 'accounts', so you can refer to them as
'accounts:login', 'accounts:logout', etc. in templates and views.
"""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("subscription/", views.subscription_view, name="subscription"),
    path("superadmin/", views.superadmin_dashboard_view, name="superadmin_dashboard"),
    path(
        "superadmin/tenant/<int:user_id>/update-plan/",
        views.superadmin_update_tenant_plan_view,
        name="superadmin_update_tenant_plan",
    ),
    path(
        "superadmin/tenant/<int:user_id>/toggle-status/",
        views.superadmin_toggle_tenant_status_view,
        name="superadmin_toggle_tenant_status",
    ),
    path(
        "superadmin/tenant/create/",
        views.superadmin_create_tenant_view,
        name="superadmin_create_tenant",
    ),
    path(
        "superadmin/tenant/<int:user_id>/add-bonus-scans/",
        views.superadmin_add_bonus_scans_view,
        name="superadmin_add_bonus_scans",
    ),
    path(
        "superadmin/payments/<int:request_id>/approve/",
        views.superadmin_approve_payment_request_view,
        name="superadmin_approve_payment_request",
    ),
    path(
        "superadmin/payments/<int:request_id>/reject/",
        views.superadmin_reject_payment_request_view,
        name="superadmin_reject_payment_request",
    ),
]
