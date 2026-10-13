"""ledger/forms.py
===============
Forms for recording payments.
"""

from decimal import Decimal

from django import forms

from billing.utils import money_round
from ledger.models import Payment


class PaymentForm(forms.ModelForm):
    """Form for recording a payment."""

    class Meta:
        model = Payment
        fields = [
            "party",
            "bill",
            "amount",
            "payment_date",
            "payment_method",
            "reference",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "w-full px-3.5 py-2.5 min-h-[44px] rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
            )

    def clean_amount(self) -> Decimal:
        amount = self.cleaned_data.get("amount")
        if amount is None or amount <= Decimal("0.00"):
            raise forms.ValidationError("Payment amount must be greater than zero.")
        return money_round(amount)
