"""bills/views.py
==============
Views for managing, creating, editing, and soft-deleting bills.
"""

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from billing.utils import money_round
from bills.forms import BillForm, BillItemFormSet
from bills.models import Bill
from bills.services import recalculate_bill_totals
from parties.models import Party


def check_can_delete_permission(user) -> None:
    """Ensure user is a superadmin, superuser, or has can_delete_records permission.

    Raises PermissionDenied (HTTP 403) if unauthorized.
    """
    is_admin = user.is_superuser or getattr(user, "is_superadmin", False)
    has_perm = getattr(user, "can_delete_records", False)
    if not (is_admin or has_perm):
        raise PermissionDenied("You do not have permission to delete or manage trashed records.")


@login_required
def bill_list_view(request: HttpRequest) -> HttpResponse:
    """Display paginated list of active bills with search and filters."""
    qs = (
        Bill.objects.select_related("party", "category")
        .prefetch_related("scan_jobs")
        .order_by("-bill_date", "-id")
    )

    # Status filter: by default, show verified and approved bills (exclude unreviewed scans)
    status_filter = request.GET.get("status", "").strip()
    if status_filter == "all":
        pass
    elif status_filter == "discrepant":
        qs = qs.filter(
            Q(has_discrepancy=True)
            | Q(
                errors__error_type__in=[
                    "math_mismatch",
                    "subtotal_mismatch",
                    "grand_total_mismatch",
                    "missing_field",
                ],
                errors__is_resolved=False,
            )
            | Q(items__unit_price__lte=0)
        ).distinct()
    elif status_filter:
        qs = qs.filter(status=status_filter)
    else:
        # Default view: only show verified/approved bills, exclude scans pending review
        qs = qs.exclude(status=Bill.Status.NEEDS_REVIEW)

    # Filters
    query = request.GET.get("q")
    if query:
        q_clean = query.strip()
        qs = qs.filter(
            Q(invoice_no__icontains=q_clean)
            | Q(party__name__icontains=q_clean)
            | Q(party__urdu_name__icontains=q_clean)
            | Q(party__phone__icontains=q_clean)
        )

    party_id = request.GET.get("party")
    if party_id:
        qs = qs.filter(party_id=party_id)

    payment_status = request.GET.get("payment_status")
    if payment_status:
        qs = qs.filter(payment_status=payment_status)

    date_filter = request.GET.get("date")
    if date_filter:
        qs = qs.filter(bill_date=date_filter)

    # Aggregates for all matching filtered bills
    total_amount = money_round(Decimal(str(qs.aggregate(total=Sum("grand_total"))["total"] or 0)))
    total_count = qs.count()

    selected_party = Party.objects.filter(pk=party_id).first() if party_id else None
    parties = Party.objects.filter(is_active=True).order_by("name")

    needs_review_count = Bill.objects.filter(status=Bill.Status.NEEDS_REVIEW).count()

    paginator = Paginator(qs, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "bills/bill_list.html",
        {
            "bills": page_obj,
            "page_obj": page_obj,
            "parties": parties,
            "selected_party": selected_party,
            "selected_party_id": party_id,
            "total_count": total_count,
            "total_amount": total_amount,
            "status_filter": status_filter,
            "needs_review_count": needs_review_count,
        },
    )


@login_required
def bill_add_view(request: HttpRequest) -> HttpResponse:
    """Create a new manual bill along with line items."""
    if request.method == "POST":
        form = BillForm(request.POST)
        has_items = "items-TOTAL_FORMS" in request.POST
        formset = BillItemFormSet(request.POST, prefix="items") if has_items else None

        if form.is_valid() and (formset is None or formset.is_valid()):
            bill = form.save(commit=False)
            bill.source = Bill.Source.MANUAL
            bill.created_by = request.user
            bill.save()

            if formset:
                for idx, item_form in enumerate(formset):
                    if item_form.cleaned_data and not item_form.cleaned_data.get("DELETE", False):
                        item = item_form.save(commit=False)
                        item.bill = bill
                        item.serial_no = idx + 1
                        item.save()

            recalculate_bill_totals(bill)
            return redirect("bills:bill_detail", pk=bill.pk)

        return render(
            request,
            "bills/bill_form.html",
            {
                "form": form,
                "formset": formset or BillItemFormSet(prefix="items"),
            },
            status=400,
        )

    form = BillForm()
    formset = BillItemFormSet(prefix="items")
    return render(request, "bills/bill_form.html", {"form": form, "formset": formset})


@login_required
def bill_detail_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Show details and line items for a bill."""
    bill = get_object_or_404(
        Bill.all_objects.select_related("party", "category").prefetch_related("items"),
        pk=pk,
    )
    return render(request, "bills/bill_detail.html", {"bill": bill})


@login_required
def bill_edit_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing bill."""
    bill = get_object_or_404(Bill.objects, pk=pk)

    if request.method == "POST":
        form = BillForm(request.POST, instance=bill)
        has_items = "items-TOTAL_FORMS" in request.POST
        formset = (
            BillItemFormSet(request.POST, instance=bill, prefix="items") if has_items else None
        )

        if form.is_valid() and (formset is None or formset.is_valid()):
            bill = form.save()
            if formset:
                formset.save()
            recalculate_bill_totals(bill)
            return redirect("bills:bill_detail", pk=bill.pk)

        return render(
            request,
            "bills/bill_form.html",
            {
                "form": form,
                "formset": formset or BillItemFormSet(instance=bill, prefix="items"),
                "bill": bill,
            },
            status=400,
        )

    form = BillForm(instance=bill)
    formset = BillItemFormSet(instance=bill, prefix="items")
    return render(
        request,
        "bills/bill_form.html",
        {"form": form, "formset": formset, "bill": bill},
    )


@login_required
def bill_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Soft delete a bill (requires can_delete_records or superadmin)."""
    check_can_delete_permission(request.user)
    bill = get_object_or_404(Bill.all_objects, pk=pk)

    if request.method == "POST":
        bill.is_deleted = True
        bill.deleted_at = timezone.now()
        bill.save(update_fields=["is_deleted", "deleted_at"])
        return redirect("bills:bill_list")

    return render(request, "bills/bill_confirm_delete.html", {"bill": bill})


@login_required
def bill_trash_view(request: HttpRequest) -> HttpResponse:
    """Display trash list of soft-deleted bills (requires permission)."""
    check_can_delete_permission(request.user)

    trashed_qs = Bill.all_objects.filter(is_deleted=True).order_by("-deleted_at")
    paginator = Paginator(trashed_qs, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "bills/bill_trash.html",
        {
            "bills": page_obj,
            "page_obj": page_obj,
        },
    )


@login_required
def bill_restore_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Restore a soft-deleted bill from trash (requires permission)."""
    check_can_delete_permission(request.user)
    bill = get_object_or_404(Bill.all_objects, pk=pk)

    if request.method == "POST":
        bill.is_deleted = False
        bill.deleted_at = None
        bill.save(update_fields=["is_deleted", "deleted_at"])
        return redirect("bills:bill_trash")

    return render(request, "bills/bill_confirm_restore.html", {"bill": bill})


@login_required
def bill_payment_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Record a payment towards a specific bill."""
    bill = get_object_or_404(Bill.all_objects, pk=pk)

    if request.method == "POST":
        from ledger.services import record_payment

        try:
            amount_str = request.POST.get("amount", "0")
            amount = Decimal(amount_str)
            payment_method = request.POST.get("payment_method", "cash")
            reference = request.POST.get("reference", "")
            notes = request.POST.get("notes", "")

            record_payment(
                party=bill.party,
                amount=amount,
                bill=bill,
                payment_method=payment_method,
                reference=reference,
                notes=notes,
                created_by=request.user,
            )
            return redirect("bills:bill_detail", pk=bill.pk)
        except Exception as e:
            return render(
                request,
                "bills/bill_payment.html",
                {"bill": bill, "error": str(e)},
                status=400,
            )

    return render(request, "bills/bill_payment.html", {"bill": bill})
