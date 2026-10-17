"""
settings_app/admin.py
================
Admin configuration for the settings_app app.
"""

from django.contrib import admin

from settings_app.models import ActivityLog, LandingPageSettings, ShopProfile


@admin.register(LandingPageSettings)
class LandingPageSettingsAdmin(admin.ModelAdmin):
    """Admin interface for managing the public landing page, video, contact info, and pricing."""

    list_display = (
        "site_title",
        "support_phone",
        "support_email",
        "whatsapp_number",
        "starter_scans",
        "pro_scans",
    )

    fieldsets = (
        (
            "🌟 Site Identity & Brand",
            {
                "fields": ("site_title", "free_scans_badge_count"),
                "description": "Brand title displayed on the marketing website.",
            },
        ),
        (
            "🚀 Hero Section (English & Urdu)",
            {
                "fields": (
                    "hero_badge_en",
                    "hero_badge_ur",
                    "hero_title_en",
                    "hero_title_ur",
                    "hero_subtitle_en",
                    "hero_subtitle_ur",
                    "hero_cta_text_en",
                    "hero_cta_text_ur",
                ),
                "description": "The top banner and main headline seen by prospective customers.",
            },
        ),
        (
            "🎬 Demo Video Settings",
            {
                "fields": (
                    "demo_video_url",
                    "video_button_text_en",
                    "video_button_text_ur",
                ),
                "description": "Paste any YouTube link (e.g. https://youtu.be/... or https://www.youtube.com/watch?v=...), Vimeo link, or MP4 URL. If empty, the interactive simulated demo will show.",
            },
        ),
        (
            "📞 Contact & Support Information",
            {
                "fields": (
                    "support_phone",
                    "support_email",
                    "whatsapp_number",
                    "contact_address",
                    "contact_hours",
                ),
                "description": "Customer contact details shown on the website, footer, and support links.",
            },
        ),
        (
            "💰 Pricing & Package Scans",
            {
                "fields": (
                    ("starter_price_pkr", "starter_price_usd", "starter_scans"),
                    ("pro_price_pkr", "pro_price_usd", "pro_scans"),
                    ("business_price_pkr", "business_price_usd", "business_scans"),
                ),
                "description": "Subscription tiers shown on the landing page pricing cards.",
            },
        ),
        (
            "🔗 Social Media Links",
            {
                "fields": (
                    "facebook_url",
                    "twitter_url",
                    "linkedin_url",
                    "instagram_url",
                    "youtube_url",
                ),
            },
        ),
        (
            "📜 Footer Notices",
            {
                "fields": ("footer_text_en", "footer_text_ur"),
            },
        ),
    )


@admin.register(ShopProfile)
class ShopProfileAdmin(admin.ModelAdmin):
    """Admin interface for the ShopProfile singleton."""

    list_display = ("name", "currency", "timezone", "daily_scan_limit", "monthly_scan_limit")


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """Read-oriented admin interface for ActivityLog audit records."""

    list_display = ("action", "user", "target_type", "target_id", "ip_address", "created_at")
    list_filter = ("action", "target_type", "created_at")
    search_fields = ("action", "description", "target_type", "user__username")
    readonly_fields = (
        "user",
        "action",
        "target_type",
        "target_id",
        "description",
        "ip_address",
        "metadata",
        "created_at",
    )
