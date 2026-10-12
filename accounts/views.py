"""
accounts/views.py
==================
Authentication views for the accounts app.

Stub views are provided here. Full login/logout logic will be
implemented in Phase 1 (Foundation).

Business logic goes in accounts/services.py — views stay thin.
"""

from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy


class LoginView(auth_views.LoginView):
    """Custom login view.

    Extends Django's built-in LoginView. Template will be added in Phase 1.
    """

    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    """Custom logout view.

    Redirects to the login page after logging out.
    """

    next_page = reverse_lazy("accounts:login")
