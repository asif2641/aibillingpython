"""bills/views.py
==============
Views for managing, creating, editing, and soft-deleting bills.
"""

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

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
    if not request.user.is_superuser:
        qs = qs.filter(Q(created_by=request.user) | Q(created_by__isnull=True))

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

    parties_qs = Party.objects.filter(is_active=True)
    if not request.user.is_superuser:
        parties_qs = parties_qs.filter(Q(user=request.user) | Q(user__isnull=True))

    selected_party = parties_qs.filter(pk=party_id).first() if party_id else None
    parties = parties_qs.order_by("name")

    needs_review_qs = Bill.objects.filter(status=Bill.Status.NEEDS_REVIEW)
    if not request.user.is_superuser:
        needs_review_qs = needs_review_qs.filter(
            Q(created_by=request.user) | Q(created_by__isnull=True)
        )
    needs_review_count = needs_review_qs.count()

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
    if not request.user.is_superuser and not request.user.has_scans_remaining:
        error_msg = _(
            "You have reached your monthly quota limit (%(used)d / %(quota)d bills). "
            "Please upgrade your plan to add or scan more bills."
        ) % {
            "used": request.user.scans_used_this_month,
            "quota": request.user.monthly_scan_quota,
        }
        messages.error(request, error_msg)
        return redirect("accounts:subscription")

    if request.method == "POST":
        form = BillForm(request.POST, user=request.user)
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
            if not request.user.is_superuser:
                request.user.increment_scans_used()
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

    form = BillForm(user=request.user)
    formset = BillItemFormSet(prefix="items")
    return render(request, "bills/bill_form.html", {"form": form, "formset": formset})


@login_required
def bill_detail_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Show details and line items for a bill."""
    bill_qs = Bill.all_objects.select_related("party", "category").prefetch_related("items")
    if not request.user.is_superuser:
        bill_qs = bill_qs.filter(Q(created_by=request.user) | Q(created_by__isnull=True))
    bill = get_object_or_404(bill_qs, pk=pk)
    return render(request, "bills/bill_detail.html", {"bill": bill})


@login_required
def bill_edit_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing bill."""
    bill_qs = Bill.objects.all()
    if not request.user.is_superuser:
        bill_qs = bill_qs.filter(Q(created_by=request.user) | Q(created_by__isnull=True))
    bill = get_object_or_404(bill_qs, pk=pk)

    if request.method == "POST":
        form = BillForm(request.POST, instance=bill, user=request.user)
        has_items = "items-TOTAL_FORMS" in request.POST
        formset = (
            BillItemFormSet(request.POST, instance=bill, prefix="items") if has_items else None
        )

        if form.is_valid() and (formset is None or formset.is_valid()):
            bill = form.save()
            if formset:
                formset.save()
            recalculate_bill_totals(bill)
            if bill.has_discrepancy or bill.had_discrepancy:
                orig_slip = (
                    bill.original_slip_total
                    if bill.original_slip_total is not None
                    else bill.grand_total
                )
                bill.has_discrepancy = False
                bill.had_discrepancy = True
                bill.discrepancy_resolved = True
                bill.discrepancy_resolved_at = timezone.now()
                date_str = timezone.now().strftime("%Y-%m-%d")
                bill.discrepancy_reason = (
                    f"Corrected on {date_str}: Previously recorded with paper slip PKR {orig_slip}. "
                    f"Corrected to actual items sum PKR {bill.grand_total}."
                )
                bill.save(
                    update_fields=[
                        "has_discrepancy",
                        "had_discrepancy",
                        "discrepancy_resolved",
                        "discrepancy_resolved_at",
                        "discrepancy_reason",
                    ]
                )
                bill.errors.filter(
                    error_type__in=[
                        "math_mismatch",
                        "subtotal_mismatch",
                        "grand_total_mismatch",
                        "missing_field",
                    ]
                ).update(is_resolved=True)
            messages.success(request, _("Bill updated and totals recalculated successfully!"))
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

    form = BillForm(instance=bill, user=request.user)
    formset = BillItemFormSet(instance=bill, prefix="items")
    return render(
        request,
        "bills/bill_form.html",
        {"form": form, "formset": formset, "bill": bill},
    )


@login_required
def bill_correct_discrepancy_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Instantly correct a discrepant bill to match line items total and resolve discrepancies."""
    bill_qs = Bill.objects.all()
    if not request.user.is_superuser:
        bill_qs = bill_qs.filter(Q(created_by=request.user) | Q(created_by__isnull=True))
    bill = get_object_or_404(bill_qs, pk=pk)
    if request.method == "POST":
        orig_slip = (
            bill.original_slip_total if bill.original_slip_total is not None else bill.grand_total
        )
        recalculate_bill_totals(bill)
        bill.has_discrepancy = False
        bill.had_discrepancy = True
        bill.discrepancy_resolved = True
        bill.discrepancy_resolved_at = timezone.now()
        date_str = timezone.now().strftime("%Y-%m-%d")
        bill.discrepancy_reason = (
            f"Corrected on {date_str}: Previously recorded with paper slip PKR {orig_slip}. "
            f"Corrected to actual items sum PKR {bill.grand_total}."
        )
        bill.status = Bill.Status.VERIFIED
        bill.save(
            update_fields=[
                "has_discrepancy",
                "had_discrepancy",
                "discrepancy_resolved",
                "discrepancy_resolved_at",
                "discrepancy_reason",
                "status",
            ]
        )
        bill.errors.filter(
            error_type__in=[
                "math_mismatch",
                "subtotal_mismatch",
                "grand_total_mismatch",
                "missing_field",
            ]
        ).update(is_resolved=True)
        messages.success(
            request,
            _(
                "Bill #%(inv)s has been corrected to PKR %(total)s and discrepancy resolved successfully!"
            )
            % {"inv": bill.invoice_no or bill.pk, "total": bill.grand_total},
        )
    return redirect("bills:bill_detail", pk=bill.pk)


@login_required
def bill_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a bill: soft-delete to trash by default, or permanently delete from database."""
    check_can_delete_permission(request.user)
    bill_qs = Bill.all_objects.all()
    if not request.user.is_superuser:
        bill_qs = bill_qs.filter(Q(created_by=request.user) | Q(created_by__isnull=True))
    bill = get_object_or_404(bill_qs, pk=pk)

    if request.method == "POST":
        permanent = request.POST.get("permanent") in ("1", "true", "True")
        invoice_display = bill.invoice_no or f"#{bill.pk}"
        party = bill.party

        if permanent:
            # Permanent hard delete: purge bill and associated files, items, errors, scan jobs
            bill.scan_jobs.all().delete()
            bill.files.all().delete()
            bill.errors.all().delete()
            bill.items.all().delete()
            bill.delete()

            if party:
                has_other_bills = party.bills.filter(is_deleted=False).exists()
                has_payments = party.payments.filter(is_deleted=False).exists()
                if not has_other_bills and not has_payments:
                    party.is_active = False
                    party.save(update_fields=["is_active"])

            messages.success(
                request,
                _("Bill %(inv)s was permanently deleted from the database.")
                % {"inv": invoice_display},
            )
            return redirect("bills:bill_list")

        # Soft delete (Move to Trash)
        bill.is_deleted = True
        bill.deleted_at = timezone.now()
        bill.save(update_fields=["is_deleted", "deleted_at"])

        # Also soft-delete payments directly attached to this bill
        bill.payments.filter(is_deleted=False).update(is_deleted=True, deleted_at=timezone.now())

        # If the party has no other active bills and no active payments, deactivate the party
        if party:
            has_other_bills = party.bills.filter(is_deleted=False).exclude(pk=bill.pk).exists()
            has_payments = party.payments.filter(is_deleted=False).exists()
            if not has_other_bills and not has_payments:
                party.is_active = False
                party.save(update_fields=["is_active"])

        messages.success(
            request,
            _("Bill #%(inv)s deleted successfully.") % {"inv": invoice_display},
        )
        return redirect("bills:bill_list")

    return render(request, "bills/bill_confirm_delete.html", {"bill": bill})


@login_required
def bill_purge_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Permanently delete a soft-deleted bill from trash (requires permission)."""
    check_can_delete_permission(request.user)
    bill_qs = Bill.all_objects.all()
    if not request.user.is_superuser:
        bill_qs = bill_qs.filter(Q(created_by=request.user) | Q(created_by__isnull=True))
    bill = get_object_or_404(bill_qs, pk=pk)

    if request.method == "POST":
        invoice_display = bill.invoice_no or f"#{bill.pk}"
        party = bill.party
        bill.scan_jobs.all().delete()
        bill.files.all().delete()
        bill.errors.all().delete()
        bill.items.all().delete()
        bill.delete()

        if party:
            has_other_bills = party.bills.filter(is_deleted=False).exists()
            has_payments = party.payments.filter(is_deleted=False).exists()
            if not has_other_bills and not has_payments:
                party.is_active = False
                party.save(update_fields=["is_active"])

        messages.success(
            request,
            _("Bill %(inv)s was permanently erased from the database.") % {"inv": invoice_display},
        )
        return redirect("bills:bill_trash")

    return redirect("bills:bill_trash")


@login_required
def bill_trash_view(request: HttpRequest) -> HttpResponse:
    """Display trash list of soft-deleted bills (requires permission)."""
    check_can_delete_permission(request.user)

    trashed_qs = Bill.all_objects.filter(is_deleted=True)
    if not request.user.is_superuser:
        trashed_qs = trashed_qs.filter(Q(created_by=request.user) | Q(created_by__isnull=True))
    trashed_qs = trashed_qs.order_by("-deleted_at")
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
    bill_qs = Bill.all_objects.all()
    if not request.user.is_superuser:
        bill_qs = bill_qs.filter(Q(created_by=request.user) | Q(created_by__isnull=True))
    bill = get_object_or_404(bill_qs, pk=pk)

    if request.method == "POST":
        bill.is_deleted = False
        bill.deleted_at = None
        bill.save(update_fields=["is_deleted", "deleted_at"])

        # Restore associated payments
        bill.payments.filter(is_deleted=True).update(is_deleted=False, deleted_at=None)

        # Reactivate party if it was deactivated
        if bill.party and not bill.party.is_active:
            bill.party.is_active = True
            bill.party.save(update_fields=["is_active"])

        messages.success(
            request,
            _("Bill #%(inv)s restored successfully.") % {"inv": bill.invoice_no or bill.pk},
        )
        return redirect("bills:bill_trash")

    return render(request, "bills/bill_confirm_restore.html", {"bill": bill})


@login_required
def bill_payment_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Record a payment towards a specific bill."""
    bill_qs = Bill.all_objects.all()
    if not request.user.is_superuser:
        bill_qs = bill_qs.filter(Q(created_by=request.user) | Q(created_by__isnull=True))
    bill = get_object_or_404(bill_qs, pk=pk)

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
