"""scanning/views.py
=================
Views for uploading documents, processing AI scans, and interactive split-screen review.
"""

import contextlib
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.clickjacking import xframe_options_sameorigin

from billing.utils import money_round
from bills.models import Bill
from bills.services import recalculate_bill_totals
from parties.models import Party
from scanning.exceptions import ScanQuotaExceededError
from scanning.models import BillEditHistory, BillFile, ScanJob
from scanning.services.extraction import process_scan_job
from scanning.services.image_processing import validate_and_preprocess_file
from scanning.services.matching import resolve_scan_party


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
        # 0. Enforce tenant scan quota
        if not request.user.has_scans_remaining:
            error_msg = _(
                "You have reached your monthly scan limit (%(used)d / %(quota)d scans). "
                "Please upgrade your plan to scan more bills."
            ) % {
                "used": request.user.scans_used_this_month,
                "quota": request.user.monthly_scan_quota,
            }
            messages.error(request, error_msg)
            return render(
                request,
                "scanning/upload.html",
                {
                    **context,
                    "quota_exceeded": True,
                    "error": error_msg,
                },
                status=403,
            )

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
            # 1. Validate and preprocess all uploaded files before database mutations
            validated_files = []
            for page_idx, uploaded_file in enumerate(files, start=1):
                processed_bytes, file_type, file_hash = validate_and_preprocess_file(uploaded_file)
                validated_files.append(
                    (uploaded_file, page_idx, file_type, processed_bytes, file_hash)
                )

            # 2. Server-Side Pre-Scan Duplicate Gate:
            # Check if any uploaded document is already scanned by this user before creating ScanJob or invoking AI
            is_forced = request.POST.get("force_rescan") == "1"
            if not is_forced:
                bill_file_filter = {
                    "bill__isnull": False,
                    "bill__is_deleted": False,
                }
                if not request.user.is_superuser:
                    bill_file_filter["bill__created_by"] = request.user

                for (
                    uploaded_file,
                    _page_idx,
                    _file_type,
                    _processed_bytes,
                    file_hash,
                ) in validated_files:
                    existing_file = (
                        BillFile.objects.filter(
                            Q(file_hash=file_hash) | Q(raw_hash=file_hash),
                            **bill_file_filter,
                        )
                        .select_related("bill__party", "scan_job")
                        .order_by("-id")
                        .first()
                    )

                    if not existing_file and uploaded_file.name:
                        clean_name = os.path.basename(uploaded_file.name)
                        existing_file = (
                            BillFile.objects.filter(
                                file__icontains=clean_name,
                                **bill_file_filter,
                            )
                            .select_related("bill__party", "scan_job")
                            .order_by("-id")
                            .first()
                        )

                    if existing_file and existing_file.bill:
                        bill = existing_file.bill
                        job = existing_file.scan_job
                        party_name = bill.party.name if bill.party else _("Unknown")
                        invoice_no = bill.invoice_no or f"#{bill.pk}"
                        dup_msg = _(
                            "Duplicate Bill Detected: This document is an identical copy of Bill %(inv)s (%(party)s, Rs. %(total)s) scanned on %(date)s."
                        ) % {
                            "inv": invoice_no,
                            "party": party_name,
                            "total": str(bill.grand_total),
                            "date": str(bill.bill_date),
                        }
                        messages.warning(request, dup_msg)
                        review_url = (
                            reverse("scanning:review", kwargs={"job_id": job.pk})
                            if job
                            else reverse("bills:bill_detail", kwargs={"pk": bill.pk})
                        )
                        detail_url = reverse("bills:bill_detail", kwargs={"pk": bill.pk})
                        return render(
                            request,
                            "scanning/upload.html",
                            {
                                **context,
                                "duplicate_detected": True,
                                "duplicate_bill": bill,
                                "duplicate_job": job,
                                "duplicate_message": dup_msg,
                                "existing_review_url": review_url,
                                "existing_detail_url": detail_url,
                            },
                            status=200,
                        )

            # 3. Create ScanJob only after all files pass quality and duplicate validation
            job = ScanJob.objects.create(
                provider=active_provider,
                status=ScanJob.Status.PENDING,
                created_by=request.user,
            )

            # 4. Attach validated pages to the job
            for uploaded_file, page_idx, file_type, processed_bytes, file_hash in validated_files:
                BillFile.objects.create(
                    scan_job=job,
                    file=uploaded_file,
                    page_number=page_idx,
                    file_type=file_type,
                    file_size=len(processed_bytes),
                    file_hash=file_hash,
                    raw_hash=file_hash,
                )

            # 5. Process scanning pipeline
            process_scan_job(job)
            request.user.increment_scans_used()
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
    filename = request.GET.get("name", "").strip().lower()

    if not file_hash or len(file_hash) < 16:
        return JsonResponse({"is_duplicate": False})

    query = Q(raw_hash=file_hash) | Q(file_hash=file_hash)
    bill_file_filter = {"bill__isnull": False, "bill__is_deleted": False}
    if not request.user.is_superuser:
        bill_file_filter["bill__created_by"] = request.user

    existing_file = (
        BillFile.objects.filter(query, **bill_file_filter)
        .select_related("bill__party", "scan_job")
        .order_by("-id")
        .first()
    )

    # Legacy fallback by filename if hash was unindexed
    if not existing_file and filename:
        clean_name = os.path.basename(filename)
        existing_file = (
            BillFile.objects.filter(
                file__icontains=clean_name,
                **bill_file_filter,
            )
            .select_related("bill__party", "scan_job")
            .order_by("-id")
            .first()
        )

    if existing_file and existing_file.bill:
        bill = existing_file.bill
        job = existing_file.scan_job
        review_url = (
            reverse("scanning:review", kwargs={"job_id": job.pk})
            if job
            else reverse("bills:bill_detail", kwargs={"pk": bill.pk})
        )
        detail_url = reverse("bills:bill_detail", kwargs={"pk": bill.pk})
        return JsonResponse(
            {
                "is_duplicate": True,
                "bill_id": bill.pk,
                "job_id": job.pk if job else None,
                "invoice_no": bill.invoice_no or f"#{bill.pk}",
                "party_name": bill.party.name if bill.party else "Unknown",
                "grand_total": str(bill.grand_total),
                "bill_date": str(bill.bill_date),
                "review_url": review_url,
                "detail_url": detail_url,
            }
        )

    return JsonResponse({"is_duplicate": False})


@login_required
def review_view(request: HttpRequest, job_id: int) -> HttpResponse:
    """Split-screen review interface: document viewer + editable bill with error alerts."""
    job_filter = {"pk": job_id}
    if not request.user.is_superuser:
        job_filter["created_by"] = request.user
    job = get_object_or_404(ScanJob, **job_filter)
    bill = job.bill

    if not bill:
        messages.error(request, _("No bill was associated with this scan."))
        return redirect("scanning:upload")

    if request.method == "POST":
        action = request.POST.get("action", "save_draft")

        if action in ("discard", "cancel"):
            # Mark bill as soft-deleted so it drops out of pending queue and calculations
            bill.is_deleted = True
            bill.deleted_at = timezone.now()
            bill.save(update_fields=["is_deleted", "deleted_at"])

            # Mark scan job status
            job.status = ScanJob.Status.FAILED
            job.error_message = "Scan discarded by user during review."
            job.save(update_fields=["status", "error_message"])

            # Resolve attached errors
            bill.errors.all().update(is_resolved=True)

            # Record audit history
            BillEditHistory.objects.create(
                bill=bill,
                user=request.user,
                field_name="status",
                old_value=bill.status,
                new_value="discarded",
            )

            invoice_display = bill.invoice_no or f"#{bill.pk}"
            messages.info(
                request,
                _("Bill %(inv)s was discarded and removed from your records.")
                % {"inv": invoice_display},
            )
            next_url = request.POST.get("next")
            if next_url:
                return redirect(next_url)
            return redirect("scanning:upload")

        # Update core invoice details
        invoice_no = request.POST.get("invoice_no", "").strip()
        bill_type_val = request.POST.get("bill_type", "").strip()
        party_name = request.POST.get("party_name", "").strip()
        party_id = request.POST.get("party")
        party_phone = request.POST.get("party_phone", "").strip()
        customer_name = request.POST.get("customer_name", "").strip()
        customer_phone = request.POST.get("customer_phone", "").strip()
        bill_date_str = request.POST.get("bill_date")
        discount_str = request.POST.get("discount", "0.00")
        tax_str = request.POST.get("tax", "0.00")

        if bill_type_val in (Bill.BillType.PURCHASE, Bill.BillType.SALE):
            bill.bill_type = bill_type_val

        customer_party = None
        if customer_name:
            customer_party, _created = resolve_scan_party(
                {"name": customer_name, "phone": customer_phone},
                party_type=Party.PartyType.CUSTOMER,
                user=request.user,
            )
            if customer_phone and customer_party.phone != customer_phone:
                customer_party.phone = customer_phone
                customer_party.save(update_fields=["phone"])

        if invoice_no:
            bill.invoice_no = invoice_no

        target_party = None
        # 1. If party_name is specified (user edited or selected)
        if party_name:
            if party_id:
                p_filter = {"pk": party_id}
                if not request.user.is_superuser:
                    p_filter["user"] = request.user
                existing = Party.objects.filter(**p_filter).first()
                if existing:
                    target_party = existing
                    if existing.name.strip().lower() != party_name.lower():
                        name_match_filter = {"name__iexact": party_name, "is_active": True}
                        if not request.user.is_superuser:
                            name_match_filter["user"] = request.user
                        name_match = Party.objects.filter(**name_match_filter).first()
                        target_party = name_match if name_match else None
            if not target_party:
                default_type = (
                    Party.PartyType.CUSTOMER
                    if bill.bill_type == Bill.BillType.SALE
                    else Party.PartyType.VENDOR
                )
                target_party, _created_party = resolve_scan_party(
                    {"name": party_name, "phone": party_phone},
                    party_type=default_type,
                    user=request.user,
                )
        elif party_id:
            p_filter = {"pk": party_id}
            if not request.user.is_superuser:
                p_filter["user"] = request.user
            target_party = Party.objects.filter(**p_filter).first()
        elif bill.bill_type == Bill.BillType.SALE and customer_party:
            target_party = customer_party

        if target_party:
            if (
                bill.bill_type == Bill.BillType.SALE
                and target_party.party_type == Party.PartyType.VENDOR
                or bill.bill_type == Bill.BillType.PURCHASE
                and target_party.party_type == Party.PartyType.CUSTOMER
            ):
                target_party.party_type = Party.PartyType.BOTH
                target_party.save(update_fields=["party_type"])

            bill.party = target_party
            if party_phone and target_party.phone != party_phone:
                target_party.phone = party_phone
                target_party.save(update_fields=["phone"])
        elif party_phone and bill.party:
            if bill.party.phone != party_phone:
                bill.party.phone = party_phone
                bill.party.save(update_fields=["phone"])

        if customer_party:
            bill.customer = customer_party
        elif not customer_name:
            bill.customer = None

        if customer_name:
            cust_note = f"Client / Customer: {customer_name}" + (
                f" ({customer_phone})" if customer_phone else ""
            )
            if cust_note not in bill.notes:
                bill.notes = (cust_note + ("\n" + bill.notes if bill.notes else "")).strip()
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
                    raw_lt = item.quantity * item.unit_price
                    integer_cand = Decimal(str(round(float(raw_lt))))
                    max_diff = max(Decimal("0.05"), money_round(item.quantity * Decimal("0.0055")))
                    if (
                        item.quantity > Decimal("1.00")
                        and abs(raw_lt - integer_cand) <= max_diff
                        and money_round(integer_cand / item.quantity) == item.unit_price
                    ):
                        item.line_total = integer_cand
                    else:
                        item.line_total = money_round(raw_lt)
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
            bill.had_discrepancy = True
            bill.discrepancy_resolved = False
            bill.discrepancy_resolved_at = None
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
    files = job.files.all().order_by("page_number", "id")
    items = list(bill.items.all())

    items_sum = money_round(sum(it.line_total for it in items))
    expected_grand_total = money_round(items_sum - bill.discount + bill.tax)

    extracted_grand_total = None
    if job.extracted_data:
        with contextlib.suppress(Exception):
            extracted_grand_total = money_round(
                Decimal(str(job.extracted_data.get("grand_total") or 0))
            )

    has_missing_price = False
    has_shortfall = bill.grand_total > Decimal("0.00") and (
        bill.grand_total - expected_grand_total > Decimal("0.05")
    )
    for it in items:
        if it.unit_price is None and it.line_total is None:
            has_missing_price = True
            break
        item_name_lower = (it.item_name or "").lower()
        if ("without price" in item_name_lower or "missing" in item_name_lower) and (
            (it.unit_price is None or it.unit_price <= Decimal("0.00"))
            and (it.line_total is None or it.line_total <= Decimal("0.00"))
        ):
            has_missing_price = True
            break
        if (
            has_shortfall
            and (it.unit_price is None or it.unit_price <= Decimal("0.00"))
            and (it.line_total is None or it.line_total <= Decimal("0.00"))
        ):
            has_missing_price = True
            break

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

    extracted_data = job.extracted_data or {}
    vendor_info = extracted_data.get("vendor") or {}
    extracted_vendor_phone = str(vendor_info.get("phone") or "").strip()
    customer_info = extracted_data.get("customer") or {}
    extracted_customer_name = str(customer_info.get("name") or "").strip()
    extracted_customer_phone = str(customer_info.get("phone") or "").strip()
    if extracted_customer_name.lower() in ("null", "none", "n/a", "unknown", "walk-in customer"):
        extracted_customer_name = ""

    if not extracted_customer_name and bill.notes and "Customer:" in bill.notes:
        import re

        m = re.search(r"Customer:\s*([^(\n]+)(?:\(([^)]+)\))?", bill.notes)
        if m:
            extracted_customer_name = m.group(1).strip()
            if m.group(2) and not extracted_customer_phone:
                extracted_customer_phone = m.group(2).strip()

    # Ensure bill.party has extracted phone if it was empty
    if bill.party and not bill.party.phone and extracted_vendor_phone:
        bill.party.phone = extracted_vendor_phone
        bill.party.save(update_fields=["phone"])

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
            "parties": Party.objects.filter(
                is_active=True,
                **({} if request.user.is_superuser else {"user": request.user}),
            ).order_by("name"),
            "extracted_vendor_phone": extracted_vendor_phone,
            "extracted_customer_name": extracted_customer_name,
            "extracted_customer_phone": extracted_customer_phone,
        },
    )


@login_required
@xframe_options_sameorigin
def file_preview_view(request: HttpRequest, file_id: int) -> HttpResponse:
    """Render high-resolution preview image for any BillFile (Image or PDF page)."""
    bill_file = get_object_or_404(BillFile, pk=file_id)

    # 1. If it's a PDF, render the target page into JPEG via PyMuPDF
    if bill_file.file_type == "pdf" or bill_file.file.name.lower().endswith(".pdf"):
        with contextlib.suppress(Exception):
            import pymupdf

            file_path = bill_file.file.path
            doc = pymupdf.open(file_path)
            target_page_idx = max(0, min(bill_file.page_number - 1, len(doc) - 1))
            page = doc[target_page_idx]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("jpeg")
            doc.close()
            return HttpResponse(img_bytes, content_type="image/jpeg")

    # 2. If it's an image or fallback, stream original file with sameorigin frame options
    try:
        content_type = "image/jpeg"
        ext = Path(bill_file.file.name).suffix.lower()
        if ext == ".png":
            content_type = "image/png"
        elif ext == ".webp":
            content_type = "image/webp"
        elif ext == ".pdf":
            content_type = "application/pdf"
        return FileResponse(bill_file.file.open("rb"), content_type=content_type)
    except Exception:
        return HttpResponseNotFound("Preview file not found.")
