"""ledger/views.py
================
Views for recording payments and managing ledger transactions.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ledger.forms import PaymentForm
from ledger.services import (
    generate_ledger_csv,
    get_all_parties_ledger_summary,
    get_party_ledger_statement,
    record_payment,
)
from parties.models import Party


@login_required
def ledger_dashboard_view(request: HttpRequest) -> HttpResponse:
    """General Ledger overview dashboard showing all party Khatas and balance summaries."""
    party_type = request.GET.get("type", "all")
    query = request.GET.get("q", "").strip()

    summary_data = get_all_parties_ledger_summary(
        party_type_filter=party_type, search_query=query, user=request.user
    )

    paginator = Paginator(summary_data["party_summaries"], 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "party_summaries": page_obj.object_list,
        "total_receivable": summary_data["total_receivable"],
        "total_payable": summary_data["total_payable"],
        "net_balance": summary_data["net_balance"],
        "total_accounts_count": summary_data["total_accounts_count"],
        "party_type": party_type,
        "query": query,
    }
    return render(request, "ledger/ledger_dashboard.html", context)


@login_required
def payment_add_view(request: HttpRequest) -> HttpResponse:
    """Record a payment towards a party or bill."""
    from decimal import Decimal

    from bills.models import Bill

    bill_qs = Bill.objects.filter(is_deleted=False)
    if not request.user.is_superuser:
        bill_qs = bill_qs.filter(created_by=request.user)

    bills_data = [
        {
            "id": b.pk,
            "party_id": b.party_id,
            "invoice_no": b.invoice_no or f"#{b.pk}",
            "grand_total": str(b.grand_total),
            "amount_due": str(max(Decimal("0.00"), b.grand_total - b.amount_paid)),
            "label": f"{b.invoice_no or f'#{b.pk}'} (Due: PKR {max(Decimal('0.00'), b.grand_total - b.amount_paid):,.2f})",
        }
        for b in bill_qs.select_related("party")
    ]

    if request.method == "POST":
        form = PaymentForm(request.POST, user=request.user)
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
                return redirect("ledger:party_ledger", party_id=payment.party.pk)
            except ValidationError as err:
                msg = str(err)
                if "Bill party does not match" in msg:
                    form.add_error("bill", err)
                else:
                    form.add_error(None, err)
                return render(
                    request,
                    "ledger/payment_form.html",
                    {"form": form, "bills_data": bills_data},
                    status=400,
                )
        return render(
            request,
            "ledger/payment_form.html",
            {"form": form, "bills_data": bills_data},
            status=400,
        )

    party_id = request.GET.get("party")
    bill_id = request.GET.get("bill")
    initial = {}
    if bill_id:
        try:
            b_obj = bill_qs.get(pk=bill_id)
            initial["bill"] = b_obj.pk
            if b_obj.party_id:
                initial["party"] = b_obj.party_id
            due = max(Decimal("0.00"), b_obj.grand_total - b_obj.amount_paid)
            if due > Decimal("0.00"):
                initial["amount"] = due
        except (Bill.DoesNotExist, ValueError):
            pass
    elif party_id:
        initial["party"] = party_id

    form = PaymentForm(initial=initial, user=request.user)
    return render(
        request,
        "ledger/payment_form.html",
        {"form": form, "bills_data": bills_data},
    )


@login_required
def party_ledger_view(request: HttpRequest, party_id: int) -> HttpResponse:
    """Render the running ledger statement (Khata) for a specific party."""
    party_qs = Party.objects.all()
    if not request.user.is_superuser:
        party_qs = party_qs.filter(user=request.user)
    party = get_object_or_404(party_qs, pk=party_id)
    statement = get_party_ledger_statement(party, user=request.user)
    context = {
        "party": party,
        "statement": statement,
    }
    return render(request, "ledger/party_ledger.html", context)


@login_required
def party_ledger_csv_view(request: HttpRequest, party_id: int) -> HttpResponse:
    """Export the party running ledger statement as a downloadable CSV."""
    party_qs = Party.objects.all()
    if not request.user.is_superuser:
        party_qs = party_qs.filter(user=request.user)
    party = get_object_or_404(party_qs, pk=party_id)
    csv_content = generate_ledger_csv(party, user=request.user)
    today_str = timezone.now().date().strftime("%Y-%m-%d")
    response = HttpResponse(csv_content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="ledger-{party.pk}-{today_str}.csv"'
    return response
