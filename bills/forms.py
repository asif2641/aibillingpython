"""bills/forms.py
===============
Forms and FormSets for creating and editing bills and bill items.
"""

from decimal import Decimal

from django import forms
from django.db.models import Q
from django.forms import inlineformset_factory

from bills.models import Bill, BillItem
from parties.models import Party


class BillForm(forms.ModelForm):
    """Form for Bill header attributes."""

    class Meta:
        model = Bill
        fields = [
            "bill_type",
            "party",
            "invoice_no",
            "bill_date",
            "bill_time",
            "category",
            "status",
            "discount",
            "tax",
            "notes",
        ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if "party" in self.fields and user is not None and not getattr(user, "is_superuser", False):
            self.fields["party"].queryset = Party.objects.filter(is_active=True).filter(
                Q(user=user) | Q(user__isnull=True)
            )
        if "status" in self.fields:
            self.fields["status"].required = False
            self.fields["status"].initial = Bill.Status.VERIFIED
        if "discount" in self.fields:
            self.fields["discount"].required = False
        if "tax" in self.fields:
            self.fields["tax"].required = False
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "w-full px-3.5 py-2 min-h-[44px] rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
            )

    def clean_status(self) -> str:
        status = self.cleaned_data.get("status")
        if not status:
            return getattr(self.instance, "status", None) or Bill.Status.VERIFIED
        return status

    def clean_discount(self) -> Decimal:
        discount = self.cleaned_data.get("discount", Decimal("0.00"))
        if discount is None:
            discount = Decimal("0.00")
        if discount < Decimal("0.00"):
            raise forms.ValidationError("Discount cannot be negative.")
        return discount

    def clean_tax(self) -> Decimal:
        tax = self.cleaned_data.get("tax", Decimal("0.00"))
        if tax is None:
            tax = Decimal("0.00")
        if tax < Decimal("0.00"):
            raise forms.ValidationError("Tax cannot be negative.")
        return tax


class BillItemForm(forms.ModelForm):
    """Form for a line item within a bill."""

    class Meta:
        model = BillItem
        fields = [
            "item_name",
            "urdu_item_name",
            "quantity",
            "unit",
            "unit_price",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "w-full px-3 py-1.5 min-h-[40px] rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-xs focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
            )


BillItemFormSet = inlineformset_factory(
    Bill,
    BillItem,
    form=BillItemForm,
    extra=1,
    can_delete=True,
)
