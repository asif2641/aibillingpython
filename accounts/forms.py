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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "placeholder": _("Enter your username"),
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "placeholder": "••••••••",
            }
        )

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


class StaffCreationForm(forms.Form):
    """Form for creating a new staff user with granular permissions."""

    username = forms.CharField(
        max_length=150,
        required=True,
        label=_("Username"),
    )
    email = forms.EmailField(
        required=False,
        label=_("Email"),
    )
    first_name = forms.CharField(
        max_length=150,
        required=False,
        label=_("First name"),
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        label=_("Last name"),
    )
    password = forms.CharField(
        widget=forms.PasswordInput,
        required=True,
        label=_("Password"),
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput,
        required=True,
        label=_("Confirm password"),
    )
    can_delete_records = forms.BooleanField(
        required=False,
        label=_("Can delete records"),
    )
    can_manage_shop = forms.BooleanField(
        required=False,
        label=_("Can manage shop"),
    )
    can_manage_categories = forms.BooleanField(
        required=False,
        label=_("Can manage categories"),
    )

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if not username:
            raise forms.ValidationError(_("Username is required."))
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError(_("A user with that username already exists."))
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", _("Passwords do not match."))

        return cleaned_data


class StaffPasswordResetForm(forms.Form):
    """Form for superadmin resetting a staff member's password."""

    new_password = forms.CharField(
        widget=forms.PasswordInput,
        required=True,
        label=_("New password"),
    )
    new_password_confirm = forms.CharField(
        widget=forms.PasswordInput,
        required=True,
        label=_("Confirm new password"),
    )

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        new_password_confirm = cleaned_data.get("new_password_confirm")

        if new_password and new_password_confirm and new_password != new_password_confirm:
            self.add_error("new_password_confirm", _("Passwords do not match."))

        return cleaned_data


class UserRegistrationForm(forms.Form):
    """Self-service registration form for new SaaS business owners."""

    business_name = forms.CharField(
        max_length=150,
        required=True,
        label=_("Business / Shop Name"),
        widget=forms.TextInput(
            attrs={
                "class": "w-full rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3.5 py-2.5 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500",
                "placeholder": _("e.g. Ali Traders or City Pharmacy"),
            }
        ),
    )
    username = forms.CharField(
        max_length=150,
        required=True,
        label=_("Username"),
        widget=forms.TextInput(
            attrs={
                "class": "w-full rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3.5 py-2.5 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500",
                "placeholder": _("Choose a unique username"),
            }
        ),
    )
    email = forms.EmailField(
        required=False,
        label=_("Email (Optional)"),
        widget=forms.EmailInput(
            attrs={
                "class": "w-full rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3.5 py-2.5 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500",
                "placeholder": "name@example.com",
            }
        ),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3.5 py-2.5 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500",
                "placeholder": "••••••••",
            }
        ),
        required=True,
        label=_("Password"),
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3.5 py-2.5 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500",
                "placeholder": "••••••••",
            }
        ),
        required=True,
        label=_("Confirm Password"),
    )

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if not username:
            raise forms.ValidationError(_("Username is required."))
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError(_("A user with that username already exists."))
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", _("Passwords do not match."))

        return cleaned_data


class SubscriptionPaymentSubmissionForm(forms.ModelForm):
    """Form for tenants to submit payment proof for subscription upgrades."""

    class Meta:
        from .models import SubscriptionPaymentRequest

        model = SubscriptionPaymentRequest
        fields = [
            "plan",
            "amount",
            "payment_method",
            "transaction_id",
            "receipt_image",
            "customer_notes",
        ]
        widgets = {
            "plan": forms.HiddenInput(),
            "amount": forms.HiddenInput(),
            "payment_method": forms.Select(
                attrs={
                    "class": "w-full rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-3.5 py-2.5 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500",
                }
            ),
            "transaction_id": forms.TextInput(
                attrs={
                    "class": "w-full rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-3.5 py-2.5 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500",
                    "placeholder": _("e.g. TID-982341 or Raast Ref #"),
                }
            ),
            "receipt_image": forms.FileInput(
                attrs={
                    "class": "w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100 dark:file:bg-slate-700 dark:file:text-slate-200",
                    "accept": "image/*",
                }
            ),
            "customer_notes": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": "w-full rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-3.5 py-2 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500",
                    "placeholder": _("Optional notes or sender account title"),
                }
            ),
        }
