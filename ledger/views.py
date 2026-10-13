"""ledger/views.py
================
Views for recording payments and managing ledger transactions.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ledger.forms import PaymentForm
from ledger.services import generate_ledger_csv, get_party_ledger_statement, record_payment
from parties.models import Party


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


@login_required
def party_ledger_view(request: HttpRequest, party_id: int) -> HttpResponse:
    """Render the running ledger statement (Khata) for a specific party."""
    party = get_object_or_404(Party, pk=party_id)
    statement = get_party_ledger_statement(party)
    context = {
        "party": party,
        "statement": statement,
    }
    return render(request, "ledger/party_ledger.html", context)


@login_required
def party_ledger_csv_view(request: HttpRequest, party_id: int) -> HttpResponse:
    """Export the party running ledger statement as a downloadable CSV."""
    party = get_object_or_404(Party, pk=party_id)
    csv_content = generate_ledger_csv(party)
    today_str = timezone.now().date().strftime("%Y-%m-%d")
    response = HttpResponse(csv_content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="ledger-{party.pk}-{today_str}.csv"'
    return response
