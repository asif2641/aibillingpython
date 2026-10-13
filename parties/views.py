"""parties/views.py
=================
Views for managing vendors and customers.
"""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from parties.forms import PartyForm
from parties.models import Party


@login_required
def vendor_list_view(request: HttpRequest) -> HttpResponse:
    """List vendors (parties of type 'vendor' or 'both'). Paginated by 25."""
    parties_qs = Party.objects.filter(party_type__in=["vendor", "both"]).order_by("name")
    paginator = Paginator(parties_qs, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "parties/vendor_list.html",
        {
            "parties": page_obj,
            "page_obj": page_obj,
            "party_type": "vendor",
        },
    )


@login_required
def customer_list_view(request: HttpRequest) -> HttpResponse:
    """List customers (parties of type 'customer' or 'both'). Paginated by 25."""
    parties_qs = Party.objects.filter(party_type__in=["customer", "both"]).order_by("name")
    paginator = Paginator(parties_qs, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "parties/customer_list.html",
        {
            "parties": page_obj,
            "page_obj": page_obj,
            "party_type": "customer",
        },
    )


@login_required
def party_add_view(request: HttpRequest) -> HttpResponse:
    """Create a new party (vendor or customer)."""
    if request.method == "POST":
        form = PartyForm(request.POST)
        if form.is_valid():
            party = form.save()
            if party.party_type == Party.PartyType.CUSTOMER:
                return redirect("parties:customer_list")
            return redirect("parties:vendor_list")
        return render(request, "parties/party_form.html", {"form": form}, status=400)

    form = PartyForm()
    return render(request, "parties/party_form.html", {"form": form})


@login_required
def party_edit_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing party."""
    party = get_object_or_404(Party, pk=pk)

    if request.method == "POST":
        form = PartyForm(request.POST, instance=party)
        if form.is_valid():
            party = form.save()
            if party.party_type == Party.PartyType.CUSTOMER:
                return redirect("parties:customer_list")
            return redirect("parties:vendor_list")
        return render(
            request,
            "parties/party_form.html",
            {"form": form, "party": party},
            status=400,
        )

    form = PartyForm(instance=party)
    return render(request, "parties/party_form.html", {"form": form, "party": party})
