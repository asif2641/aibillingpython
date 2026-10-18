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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        from bills.models import Bill
        from parties.models import Party

        party_qs = Party.objects.filter(is_active=True)
        bill_qs = Bill.objects.filter(is_deleted=False)

        if user is not None and not getattr(user, "is_superuser", False):
            party_qs = party_qs.filter(user=user)
            bill_qs = bill_qs.filter(created_by=user)

        if "party" in self.fields:
            self.fields["party"].queryset = party_qs

        # Determine target party if available
        party_id = None
        if self.data and "party" in self.data:
            party_id = self.data.get("party")
        elif "initial" in kwargs and kwargs["initial"] and "party" in kwargs["initial"]:
            party_id = kwargs["initial"]["party"]
            if hasattr(party_id, "pk"):
                party_id = party_id.pk
        elif self.instance and self.instance.pk and self.instance.party_id:
            party_id = self.instance.party_id

        if party_id:
            bill_qs = bill_qs.filter(party_id=party_id)

        if "bill" in self.fields:
            self.fields["bill"].queryset = bill_qs
            self.fields["bill"].required = False
            self.fields[
                "bill"
            ].empty_label = "--- Optional: On-account credit (no specific bill) ---"

            def _bill_label(obj):
                due = max(Decimal("0.00"), obj.grand_total - obj.amount_paid)
                inv = obj.invoice_no or f"Bill #{obj.pk}"
                return f"{inv} — Due: PKR {due:,.2f} (Total: {obj.grand_total:,.2f})"

            self.fields["bill"].label_from_instance = _bill_label

        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "w-full px-3.5 py-2.5 min-h-[44px] rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
            )

    def clean(self):
        cleaned_data = super().clean()
        party = cleaned_data.get("party")
        bill = cleaned_data.get("bill")
        if party and bill and bill.party_id != party.pk:
            self.add_error(
                "bill", forms.ValidationError("Bill party does not match payment party.")
            )
        return cleaned_data

    def clean_amount(self) -> Decimal:
        amount = self.cleaned_data.get("amount")
        if amount is None or amount <= Decimal("0.00"):
            raise forms.ValidationError("Payment amount must be greater than zero.")
        return money_round(amount)
