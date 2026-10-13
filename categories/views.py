"""
categories/views.py
===================
Views for Category and Unit management with granular permission enforcement.
"""

from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .forms import CategoryForm, UnitForm
from .models import Category, Unit


def category_management_required(view_func):
    """Decorator requiring login and either superadmin or can_manage_categories permission."""

    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        is_super = (
            user.is_superuser
            or getattr(user, "is_superadmin", False)
            or getattr(user, "role", "") == "superadmin"
        )
        can_manage = getattr(user, "can_manage_categories", False)
        if not (is_super or can_manage):
            return HttpResponseForbidden(
                "You do not have permission to manage categories or units."
            )
        return view_func(request, *args, **kwargs)

    return _wrapped_view


@category_management_required
def category_list_view(request):
    """List all categories with pagination."""
    categories_qs = Category.objects.all().order_by("name")
    paginator = Paginator(categories_qs, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(
        request,
        "categories/category_list.html",
        {
            "page_obj": page_obj,
            "categories": page_obj.object_list,
        },
    )


@category_management_required
def category_add_view(request):
    """Create a new category."""
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(request, _(f"Category '{category.name}' created successfully."))
            try:
                return redirect(reverse("categories:category_list"))
            except Exception:
                return redirect("/en/categories/")
        return render(request, "categories/category_form.html", {"form": form}, status=400)

    form = CategoryForm()
    return render(request, "categories/category_form.html", {"form": form})


@category_management_required
def category_edit_view(request, pk: int):
    """Edit an existing category."""
    category = get_object_or_404(Category, pk=pk)

    if request.method == "POST":
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, _(f"Category '{category.name}' updated successfully."))
            try:
                return redirect(reverse("categories:category_list"))
            except Exception:
                return redirect("/en/categories/")
        return render(
            request,
            "categories/category_form.html",
            {"form": form, "category": category},
            status=400,
        )

    form = CategoryForm(instance=category)
    return render(
        request,
        "categories/category_form.html",
        {"form": form, "category": category},
    )


@category_management_required
def category_archive_view(request, pk: int):
    """Toggle is_archived state on an existing category."""
    category = get_object_or_404(Category, pk=pk)
    category.is_archived = not category.is_archived
    category.save(update_fields=["is_archived"])
    status_text = _("archived") if category.is_archived else _("restored")
    messages.success(request, _(f"Category '{category.name}' {status_text} successfully."))
    try:
        return redirect(reverse("categories:category_list"))
    except Exception:
        return redirect("/en/categories/")


@category_management_required
def unit_list_view(request):
    """List all units of measure with pagination."""
    units_qs = Unit.objects.all().order_by("name")
    paginator = Paginator(units_qs, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(
        request,
        "categories/unit_list.html",
        {
            "page_obj": page_obj,
            "units": page_obj.object_list,
        },
    )


@category_management_required
def unit_add_view(request):
    """Create a new custom unit of measurement."""
    if request.method == "POST":
        form = UnitForm(request.POST)
        if form.is_valid():
            unit = form.save()
            messages.success(request, _(f"Unit '{unit.name}' added successfully."))
            try:
                return redirect(reverse("categories:unit_list"))
            except Exception:
                return redirect("/en/categories/units/")
        return render(request, "categories/unit_form.html", {"form": form}, status=400)

    form = UnitForm()
    return render(request, "categories/unit_form.html", {"form": form})
