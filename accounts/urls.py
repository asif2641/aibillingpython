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
]
