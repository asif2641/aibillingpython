"""
settings_app/views.py
=====================
Views for the settings_app application.
"""

from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from .forms import ShopProfileForm
from .models import ShopProfile


def shop_management_required(view_func):
    """Decorator requiring login and either superadmin or can_manage_shop permission."""

    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        is_super = (
            user.is_superuser
            or getattr(user, "is_superadmin", False)
            or getattr(user, "role", "") == "superadmin"
        )
        can_manage = getattr(user, "can_manage_shop", False)
        if not (is_super or can_manage):
            return HttpResponseForbidden("You do not have permission to manage shop settings.")
        return view_func(request, *args, **kwargs)

    return _wrapped_view


@shop_management_required
def shop_profile_view(request):
    """View and update shop profile singleton configuration."""
    profile = ShopProfile.get_solo()

    if request.method == "POST":
        form = ShopProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, _("Shop profile updated successfully."))
            return redirect(request.path)
        return render(
            request,
            "settings_app/shop_profile.html",
            {"form": form, "profile": profile, "active_tab": "shop"},
            status=400,
        )

    form = ShopProfileForm(instance=profile)
    return render(
        request,
        "settings_app/shop_profile.html",
        {"form": form, "profile": profile, "active_tab": "shop"},
    )
