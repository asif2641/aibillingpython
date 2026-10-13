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
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

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

        recalculate_bill_totals(bill)

        # Audit history log
        BillEditHistory.objects.create(
            bill=bill,
            user=request.user,
            field_name="status",
            old_value=bill.status,
            new_value=Bill.Status.VERIFIED if action == "verify" else Bill.Status.DRAFT,
        )

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

    return render(
        request,
        "scanning/review.html",
        {
            "job": job,
            "bill": bill,
            "items": bill.items.all(),
            "errors": errors,
            "files": files,
            "parties": Party.objects.filter(is_active=True).order_by("name"),
        },
    )
