"""parties/views.py
=================
Views for managing vendors and customers.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from parties.forms import PartyForm
from parties.models import Party


@login_required
def vendor_list_view(request: HttpRequest) -> HttpResponse:
    """List active vendors (parties of type 'vendor' or 'both'). Paginated by 25."""
    parties_qs = Party.objects.filter(party_type__in=["vendor", "both"], is_active=True)
    if not request.user.is_superuser:
        parties_qs = parties_qs.filter(user=request.user)
    parties_qs = parties_qs.order_by("name")

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
    """List active customers (parties of type 'customer' or 'both'). Paginated by 25."""
    parties_qs = Party.objects.filter(party_type__in=["customer", "both"], is_active=True)
    if not request.user.is_superuser:
        parties_qs = parties_qs.filter(user=request.user)
    parties_qs = parties_qs.order_by("name")

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
def party_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Deactivate / delete a party so it no longer appears in active vendor/customer lists."""
    if request.user.is_superuser:
        party = get_object_or_404(Party, pk=pk)
    else:
        party = get_object_or_404(Party.objects.filter(user=request.user), pk=pk)

    target = (
        "parties:customer_list"
        if party.party_type == Party.PartyType.CUSTOMER
        else "parties:vendor_list"
    )

    if request.method == "POST":
        party.is_active = False
        party.save(update_fields=["is_active"])
        messages.success(
            request,
            _("Party '%(name)s' deleted successfully.") % {"name": party.name},
        )
        return redirect(target)

    return redirect(target)


@login_required
def party_add_view(request: HttpRequest) -> HttpResponse:
    """Create a new party (vendor or customer)."""
    if request.method == "POST":
        form = PartyForm(request.POST)
        if form.is_valid():
            party = form.save(commit=False)
            party.user = request.user
            party.save()
            if party.party_type == Party.PartyType.CUSTOMER:
                return redirect("parties:customer_list")
            return redirect("parties:vendor_list")
        return render(request, "parties/party_form.html", {"form": form}, status=400)

    form = PartyForm()
    return render(request, "parties/party_form.html", {"form": form})


@login_required
def party_edit_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing party."""
    if request.user.is_superuser:
        party = get_object_or_404(Party, pk=pk)
    else:
        party = get_object_or_404(Party.objects.filter(user=request.user), pk=pk)

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
