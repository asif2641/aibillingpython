"""
accounts/views.py
=================
Authentication views for the accounts app.

Provides LoginView with 5-attempt failed login lockout enforcement and
LogoutView redirecting to login.

Business logic resides in accounts/services.py — views stay thin.
"""

from __future__ import annotations

from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy

from .forms import CustomAuthenticationForm


class LoginView(auth_views.LoginView):
    """Custom login view with 5-attempt account lockout.

    Uses CustomAuthenticationForm which interfaces with accounts.services
    to record failed attempts, lock accounts after 5 failures, and auto-unlock
    after 15 minutes.
    """

    form_class = CustomAuthenticationForm
    authentication_form = CustomAuthenticationForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True
    next_page = reverse_lazy("dashboard")


class LogoutView(auth_views.LogoutView):
    """Custom logout view.

    Terminates the user session and redirects to the login page.
    """

    next_page = reverse_lazy("accounts:login")
