"""scanning/views.py
=================
Views for uploading documents, processing AI scans, and interactive split-screen review.
"""

import contextlib
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from billing.utils import money_round
from bills.models import Bill
from bills.services import recalculate_bill_totals
from parties.models import Party
from scanning.exceptions import ScanQuotaExceededError
from scanning.models import BillEditHistory, BillFile, ScanJob
from scanning.services.extraction import process_scan_job
from scanning.services.image_processing import validate_and_preprocess_file


@login_required
def upload_view(request: HttpRequest) -> HttpResponse:
    """Upload bill files (single, multi-page image, or PDF) and initiate scan."""
    active_provider = getattr(settings, "AI_PROVIDER", "gemini")
    gemini_key = getattr(settings, "GEMINI_API_KEY", "")
    claude_key = getattr(settings, "CLAUDE_API_KEY", "")

    api_key_configured = True
    if (
        active_provider == "gemini"
        and not gemini_key
        or active_provider == "claude"
        and not claude_key
    ):
        api_key_configured = False

    context = {
        "api_key_configured": api_key_configured,
        "active_provider": active_provider,
    }

    if request.method == "POST":
        files = request.FILES.getlist("files")
        if not files:
            messages.error(request, _("Please select at least one document or photo to scan."))
            return render(request, "scanning/upload.html", context, status=400)

        if not api_key_configured and active_provider != "mock":
            error_msg = _(
                "AI extraction requires a valid Gemini API key. Please add GEMINI_API_KEY to your .env file "
                "(get a free key from https://aistudio.google.com), or set AI_PROVIDER=mock in .env for offline testing."
            )
            messages.error(request, error_msg)
            return render(
                request, "scanning/upload.html", {**context, "error": error_msg}, status=400
            )

        try:
            # Create ScanJob using active configured provider
            job = ScanJob.objects.create(
                provider=active_provider,
                status=ScanJob.Status.PENDING,
                created_by=request.user,
            )

            # Process and attach each uploaded page
            for page_idx, uploaded_file in enumerate(files, start=1):
                processed_bytes, file_type, file_hash = validate_and_preprocess_file(uploaded_file)
                BillFile.objects.create(
                    scan_job=job,
                    file=uploaded_file,
                    page_number=page_idx,
                    file_type=file_type,
                    file_size=len(processed_bytes),
                    file_hash=file_hash,
                )

            # Process scanning pipeline
            process_scan_job(job)
            return redirect("scanning:review", job_id=job.pk)

        except (ValidationError, ScanQuotaExceededError) as err:
            error_msg = str(err.messages[0] if hasattr(err, "messages") else err)
            messages.error(request, error_msg)
            return render(
                request, "scanning/upload.html", {**context, "error": error_msg}, status=400
            )
        except Exception as exc:
            messages.error(request, _("Scanning failed: %(err)s") % {"err": str(exc)})
            return render(
                request, "scanning/upload.html", {**context, "error": str(exc)}, status=400
            )

    return render(request, "scanning/upload.html", context)


@login_required
def check_duplicate_view(request: HttpRequest) -> JsonResponse:
    """Instant check if an uploaded file hash matches an existing scanned bill."""
    file_hash = request.GET.get("hash", "").strip().lower()
    if not file_hash or len(file_hash) < 16:
        return JsonResponse({"is_duplicate": False})

    existing_file = (
        BillFile.objects.filter(file_hash=file_hash, bill__isnull=False, bill__is_deleted=False)
        .select_related("bill__party", "scan_job")
        .order_by("-id")
        .first()
    )

    if existing_file and existing_file.bill:
        bill = existing_file.bill
        job = existing_file.scan_job
        return JsonResponse(
            {
                "is_duplicate": True,
                "bill_id": bill.pk,
                "job_id": job.pk if job else None,
                "invoice_no": bill.invoice_no or f"#{bill.pk}",
                "party_name": bill.party.name if bill.party else "Unknown",
                "grand_total": str(bill.grand_total),
                "bill_date": str(bill.bill_date),
                "review_url": f"/en/scanning/review/{job.pk}/" if job else f"/en/bills/{bill.pk}/",
                "detail_url": f"/en/bills/{bill.pk}/",
            }
        )

    return JsonResponse({"is_duplicate": False})


@login_required
def review_view(request: HttpRequest, job_id: int) -> HttpResponse:
    """Split-screen review interface: document viewer + editable bill with error alerts."""
    job = get_object_or_404(ScanJob, pk=job_id)
    bill = job.bill

    if not bill:
        messages.error(request, _("No bill was associated with this scan."))
        return redirect("scanning:upload")

    if request.method == "POST":
        action = request.POST.get("action", "save_draft")

        # Update core invoice details
        invoice_no = request.POST.get("invoice_no", "").strip()
        party_id = request.POST.get("party")
        party_phone = request.POST.get("party_phone", "").strip()
        bill_date_str = request.POST.get("bill_date")
        discount_str = request.POST.get("discount", "0.00")
        tax_str = request.POST.get("tax", "0.00")

        if invoice_no:
            bill.invoice_no = invoice_no
        if party_id:
            party = Party.objects.filter(pk=party_id).first()
            if party:
                bill.party = party
                if party_phone and party.phone != party_phone:
                    party.phone = party_phone
                    party.save(update_fields=["phone"])
        elif party_phone and bill.party:
            if bill.party.phone != party_phone:
                bill.party.phone = party_phone
                bill.party.save(update_fields=["phone"])
        if bill_date_str:
            with contextlib.suppress(ValueError, TypeError):
                bill.bill_date = timezone.datetime.strptime(bill_date_str[:10], "%Y-%m-%d").date()

        with contextlib.suppress(ValueError, TypeError, InvalidOperation):
            bill.discount = Decimal(discount_str or "0.00")
            bill.tax = Decimal(tax_str or "0.00")

        # Update line items if submitted from review table
        item_ids = request.POST.getlist("item_id")
        for item_id in item_ids:
            with contextlib.suppress(Exception):
                item = bill.items.filter(pk=item_id).first()
                if item:
                    item_name_val = request.POST.get(f"item_name_{item_id}", "").strip()
                    item_qty_val = request.POST.get(f"item_qty_{item_id}", "").strip()
                    item_price_val = request.POST.get(f"item_price_{item_id}", "").strip()

                    if item_name_val:
                        item.item_name = item_name_val
                    if item_qty_val:
                        item.quantity = Decimal(item_qty_val)
                    if item_price_val:
                        item.unit_price = money_round(Decimal(item_price_val))
                    item.line_total = money_round(item.quantity * item.unit_price)
                    item.save()

        recalculate_bill_totals(bill)

        # Audit history log
        new_status = (
            Bill.Status.VERIFIED
            if action in ("verify", "correct_and_go", "accept_incorrect")
            else Bill.Status.DRAFT
        )
        BillEditHistory.objects.create(
            bill=bill,
            user=request.user,
            field_name="status",
            old_value=bill.status,
            new_value=new_status,
        )

        items_sum = money_round(sum(it.line_total for it in bill.items.all()))
        computed_grand_total = money_round(items_sum - bill.discount + bill.tax)

        if action == "correct_and_go":
            # Option 2: Correct & Go -> Update bill to mathematically correct items total and verify
            bill.subtotal = items_sum
            bill.grand_total = computed_grand_total
            bill.has_discrepancy = False
            bill.discrepancy_reason = ""
            bill.status = Bill.Status.VERIFIED
            bill.save()
            bill.errors.filter(
                error_type__in=["math_mismatch", "subtotal_mismatch", "grand_total_mismatch"]
            ).update(is_resolved=True)
            messages.success(
                request,
                _("Bill total was corrected to PKR %(total)s and approved successfully!")
                % {"total": bill.grand_total},
            )
            return redirect("bills:bill_detail", pk=bill.pk)

        if action == "accept_incorrect":
            # Option 1: Go with Incorrect Bill -> Keep the handwritten / slip total and record discrepancy
            slip_total_raw = request.POST.get("original_slip_total") or request.POST.get(
                "grand_total"
            )
            try:
                slip_total = money_round(Decimal(str(slip_total_raw)))
            except Exception:
                slip_total = bill.grand_total

            bill.original_slip_total = slip_total
            bill.grand_total = slip_total
            bill.has_discrepancy = True
            diff = money_round(slip_total - computed_grand_total)
            bill.discrepancy_reason = (
                f"Accepted incorrect bill: Paper slip total was PKR {slip_total} "
                f"while items sum was PKR {computed_grand_total} (Difference: PKR {diff})."
            )
            bill.status = Bill.Status.VERIFIED
            bill.save()
            messages.warning(
                request,
                _(
                    "Bill approved with original slip total (PKR %(total)s). Recorded in Incorrect Bills log."
                )
                % {"total": bill.grand_total},
            )
            return redirect("bills:bill_detail", pk=bill.pk)

        if action == "verify":
            bill.status = Bill.Status.VERIFIED
            bill.save()
            # Resolve all attached errors
            bill.errors.update(is_resolved=True)
            messages.success(request, _("Bill verified and saved successfully!"))
            return redirect("bills:bill_detail", pk=bill.pk)

        bill.status = Bill.Status.DRAFT
        bill.save()
        messages.info(request, _("Bill saved as Draft."))
        return redirect("bills:bill_detail", pk=bill.pk)

    errors = bill.errors.filter(is_resolved=False)
    files = job.files.all()
    items = list(bill.items.all())

    items_sum = money_round(sum(it.line_total for it in items))
    expected_grand_total = money_round(items_sum - bill.discount + bill.tax)

    extracted_grand_total = None
    if job.extracted_data:
        with contextlib.suppress(Exception):
            extracted_grand_total = money_round(
                Decimal(str(job.extracted_data.get("grand_total") or 0))
            )

    has_missing_price = any(
        (it.unit_price is None or it.unit_price <= Decimal("0.00"))
        and (it.line_total is None or it.line_total <= Decimal("0.00"))
        for it in items
    )

    has_total_mismatch = (
        abs(expected_grand_total - bill.grand_total) > Decimal("0.05")
        or (
            extracted_grand_total is not None
            and abs(extracted_grand_total - expected_grand_total) > Decimal("0.05")
        )
        or errors.filter(
            error_type__in=["grand_total_mismatch", "subtotal_mismatch", "math_mismatch"]
        ).exists()
    )

    is_total_invalid = has_total_mismatch or has_missing_price

    return render(
        request,
        "scanning/review.html",
        {
            "job": job,
            "bill": bill,
            "items": items,
            "items_sum": items_sum,
            "expected_grand_total": expected_grand_total,
            "extracted_grand_total": extracted_grand_total,
            "has_missing_price": has_missing_price,
            "has_total_mismatch": has_total_mismatch,
            "is_total_invalid": is_total_invalid,
            "errors": errors,
            "files": files,
            "parties": Party.objects.filter(is_active=True).order_by("name"),
        },
    )
