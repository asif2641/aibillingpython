"""bills/forms.py
===============
Forms and FormSets for creating and editing bills and bill items.
"""

from decimal import Decimal

from django import forms
from django.db.models import Q
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from bills.models import Bill, BillItem
from parties.models import Party


class BillForm(forms.ModelForm):
    """Form for Bill header attributes supporting dropdown selection and manual text entry."""

    party_name = forms.CharField(
        required=False,
        max_length=255,
        label=_("Vendor / Customer Name"),
    )
    category_name = forms.CharField(
        required=False,
        max_length=100,
        label=_("Category Name"),
    )

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
        self.user = user
        super().__init__(*args, **kwargs)

        if "party" in self.fields:
            self.fields["party"].required = False
            if user is not None and not getattr(user, "is_superuser", False):
                self.fields["party"].queryset = Party.objects.filter(is_active=True).filter(
                    Q(user=user) | Q(user__isnull=True)
                )

        if "category" in self.fields:
            self.fields["category"].required = False

        if "status" in self.fields:
            self.fields["status"].required = False
            self.fields["status"].initial = Bill.Status.VERIFIED

        if "discount" in self.fields:
            self.fields["discount"].required = False

        if "tax" in self.fields:
            self.fields["tax"].required = False

        # Prepopulate initial text names when editing existing bill
        if self.instance and self.instance.pk:
            if self.instance.party and "party_name" in self.fields:
                self.fields["party_name"].initial = self.instance.party.name
            if self.instance.category and "category_name" in self.fields:
                self.fields["category_name"].initial = self.instance.category.name

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

    def clean(self):
        cleaned_data = super().clean()
        party = cleaned_data.get("party")
        party_name = (self.data.get("party_name") or cleaned_data.get("party_name") or "").strip()
        bill_type = cleaned_data.get("bill_type") or getattr(
            self.instance, "bill_type", Bill.BillType.PURCHASE
        )

        # 1. Resolve Party (Vendor or Customer) from text input or dropdown
        if party_name and (not party or party.name.strip().lower() != party_name.lower()):
            from parties.services import match_or_create_party

            party_type = (
                Party.PartyType.CUSTOMER
                if bill_type == Bill.BillType.SALE
                else Party.PartyType.VENDOR
            )
            party = match_or_create_party(
                name=party_name,
                party_type=party_type,
                user=self.user,
            )
            cleaned_data["party"] = party
        elif not party and not party_name:
            self.add_error("party", _("Please select or enter a vendor or customer name."))

        # 2. Resolve Category from manual entry or dropdown
        category = cleaned_data.get("category")
        category_name = (
            self.data.get("category_name") or cleaned_data.get("category_name") or ""
        ).strip()
        if category_name and (
            not category or category.name.strip().lower() != category_name.lower()
        ):
            from categories.models import Category

            category = Category.objects.filter(name__iexact=category_name).first()
            if not category:
                category = Category.objects.create(name=category_name)
            cleaned_data["category"] = category

        return cleaned_data


class BillItemForm(forms.ModelForm):
    """Form for a line item within a bill supporting item selection and autocomplete."""

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
        if "item_name" in self.fields:
            self.fields["item_name"].widget.attrs["list"] = "bill_items_datalist"
            self.fields["item_name"].widget.attrs["placeholder"] = _("Select or type item name...")
            self.fields["item_name"].widget.attrs["autocomplete"] = "off"
        if "unit" in self.fields:
            self.fields["unit"].widget.attrs["list"] = "bill_units_datalist"
            self.fields["unit"].widget.attrs["placeholder"] = "pcs, kg, etc."
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
