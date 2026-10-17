"""settings_app/context_processors.py
===================================
Context processor exposing global landing page settings and shop profile singleton
to all templates across the application.
"""

from __future__ import annotations

from .models import LandingPageSettings, ShopProfile


def site_settings(request):
    """Make LandingPageSettings and ShopProfile available in all template contexts."""
    try:
        landing_obj = LandingPageSettings.get_solo()
    except Exception:
        landing_obj = None

    try:
        profile_obj = ShopProfile.get_solo()
    except Exception:
        profile_obj = None

    return {
        "site_settings": landing_obj,
        "shop_profile": profile_obj,
    }
