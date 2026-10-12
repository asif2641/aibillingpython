"""
aibilling/views.py
==================
Project-level views for the aibilling application.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def dashboard_view(request):
    """Render the main dashboard layout shell.

    Requires authentication; unauthenticated users are redirected
    to the login page by the @login_required decorator.
    """
    context = {
        "title": "Dashboard",
        "total_spend": 0,
        "total_bills": 0,
        "outstanding_credit": 0,
        "average_bill": 0,
    }
    return render(request, "dashboard/index.html", context)
