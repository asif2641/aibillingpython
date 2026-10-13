"""
sync/views.py
=============
API views for offline synchronization queue push, pull, and status check.
"""

from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from sync.models import SyncQueue
from sync.services import sync_pull_service, sync_push_service


@csrf_exempt
@require_POST
@login_required
def sync_push_view(request: HttpRequest) -> JsonResponse:
    """Process a batch of offline synchronization queue items pushed by client.

    Accepts JSON body with either {"items": [...]} or a top-level list [...].
    Returns JSON summary with success status, processed items, and failed items.
    """
    try:
        payload: Any = json.loads(request.body.decode("utf-8")) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("items", [])
    else:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not isinstance(items, list):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    summary = sync_push_service(request.user, items)
    return JsonResponse(summary)


@require_GET
@login_required
def sync_pull_view(request: HttpRequest) -> JsonResponse:
    """Return serialized reference data (parties, categories, units) for offline PWA caching.

    Accepts optional GET query parameter 'since' to filter changes since a given timestamp.
    """
    since = request.GET.get("since")
    data = sync_pull_service(request.user, since=since)
    return JsonResponse(data)


@login_required
def sync_status_view(request: HttpRequest) -> JsonResponse:
    """Return current user's synchronization queue status summary counts."""
    pending_count = SyncQueue.objects.filter(
        user=request.user, status=SyncQueue.Status.PENDING
    ).count()
    processed_count = SyncQueue.objects.filter(
        user=request.user, status=SyncQueue.Status.PROCESSED
    ).count()
    failed_count = SyncQueue.objects.filter(
        user=request.user, status=SyncQueue.Status.FAILED
    ).count()

    return JsonResponse(
        {
            "pending": pending_count,
            "processed": processed_count,
            "failed": failed_count,
        }
    )
