"""ledger/views.py
================
Views for recording payments and managing ledger transactions.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from ledger.forms import PaymentForm
from ledger.services import record_payment


@login_required
def payment_add_view(request: HttpRequest) -> HttpResponse:
    """Record a payment towards a party or bill."""
    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            try:
                payment = record_payment(
                    party=form.cleaned_data["party"],
                    amount=form.cleaned_data["amount"],
                    bill=form.cleaned_data.get("bill"),
                    payment_date=form.cleaned_data.get("payment_date"),
                    payment_method=form.cleaned_data.get("payment_method", "cash"),
                    reference=form.cleaned_data.get("reference", ""),
                    notes=form.cleaned_data.get("notes", ""),
                    created_by=request.user,
                )
                if payment.bill:
                    return redirect("bills:bill_detail", pk=payment.bill.pk)
                return redirect("ledger:payment_add")
            except ValidationError as err:
                form.add_error(None, err)
                return render(request, "ledger/payment_form.html", {"form": form}, status=400)
        return render(request, "ledger/payment_form.html", {"form": form}, status=400)

    form = PaymentForm()
    return render(request, "ledger/payment_form.html", {"form": form})
