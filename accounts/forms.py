"""
accounts/forms.py
=================
Authentication forms for the accounts app.

Provides CustomAuthenticationForm which integrates with accounts.services
to enforce 5-attempt failed login lockout and automatic unlock after 15 minutes.
"""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _

from .services import is_account_locked, record_failed_login, record_successful_login

LOCKOUT_ERROR_MESSAGE = _(
    "Your account is locked due to 5 consecutive failed login attempts. "
    "Please try again after 15 minutes."
)


class CustomAuthenticationForm(AuthenticationForm):
    """Authentication form enforcing the 5-attempt account lockout policy."""

    def clean(self):
        """Validate credentials and enforce account lockout rules."""
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if not username or not password:
            return self.cleaned_data

        UserModel = get_user_model()
        try:
            user = UserModel._default_manager.get_by_natural_key(username)
        except UserModel.DoesNotExist:
            user = None

        if user is not None and is_account_locked(user):
            if self.request is not None:
                messages.error(self.request, LOCKOUT_ERROR_MESSAGE)
            raise forms.ValidationError(
                LOCKOUT_ERROR_MESSAGE,
                code="account_locked",
            )

        self.user_cache = authenticate(
            self.request,
            username=username,
            password=password,
        )

        if self.user_cache is None:
            if user is not None:
                record_failed_login(user)
                if user.is_locked:
                    if self.request is not None:
                        messages.error(self.request, LOCKOUT_ERROR_MESSAGE)
                    raise forms.ValidationError(
                        LOCKOUT_ERROR_MESSAGE,
                        code="account_locked",
                    )
            raise forms.ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
                params={"username": self.username_field.verbose_name},
            )

        self.confirm_login_allowed(self.user_cache)
        record_successful_login(self.user_cache)

        return self.cleaned_data
