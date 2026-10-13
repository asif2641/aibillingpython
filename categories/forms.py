"""
categories/forms.py
===================
Forms for Category and Unit management.
"""

from __future__ import annotations

import re

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import HEX_COLOR_REGEX, Category, Unit


class CategoryForm(forms.ModelForm):
    """Form for creating and editing billing item categories."""

    class Meta:
        model = Category
        fields = ["name", "urdu_name", "color"]
        widgets = {
            "color": forms.TextInput(
                attrs={"type": "color", "class": "form-control form-control-color"}
            ),
        }

    def clean_name(self) -> str:
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError(_("Category name is required."))
        return name

    def clean_color(self) -> str:
        color = self.cleaned_data.get("color", "").strip()
        if not color or not re.match(HEX_COLOR_REGEX, color):
            raise forms.ValidationError(_("Enter a valid hex color code (e.g. #3B82F6)."))
        return color


class UnitForm(forms.ModelForm):
    """Form for creating custom measurement units."""

    class Meta:
        model = Unit
        fields = ["name", "code", "urdu_name"]

    def clean_name(self) -> str:
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError(_("Unit name is required."))
        return name

    def clean_code(self) -> str:
        code = self.cleaned_data.get("code", "").strip()
        if not code:
            raise forms.ValidationError(_("Unit code is required."))
        return code
