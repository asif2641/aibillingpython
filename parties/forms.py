"""parties/forms.py
=================
Forms for creating and updating Party instances.
"""

from django import forms

from parties.models import Party


class PartyForm(forms.ModelForm):
    """Form for adding and editing vendors and customers."""

    class Meta:
        model = Party
        fields = [
            "name",
            "urdu_name",
            "phone",
            "email",
            "address",
            "tax_number",
            "party_type",
            "notes",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != "is_active":
                field.widget.attrs["class"] = (
                    "w-full px-3.5 py-2.5 min-h-[44px] rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
                )
            else:
                field.widget.attrs["class"] = (
                    "w-4 h-4 text-primary-600 rounded border-slate-300 focus:ring-primary-500"
                )

    def clean_name(self) -> str:
        name = self.cleaned_data.get("name", "")
        if not name or not name.strip():
            raise forms.ValidationError("Party name is required.")
        return name.strip()
