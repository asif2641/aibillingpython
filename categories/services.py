"""
categories/services.py
======================
Service functions and data seeding for Category and Unit models.
"""

from __future__ import annotations

from .models import Category, Unit

DEFAULT_CATEGORIES = [
    {"name": "Grocery", "urdu_name": "کریانہ", "color": "#10B981"},
    {"name": "Medical", "urdu_name": "ادویات", "color": "#EF4444"},
    {"name": "Utilities", "urdu_name": "یوٹیلیٹیز", "color": "#F59E0B"},
    {"name": "Fuel", "urdu_name": "فیول", "color": "#6366F1"},
    {"name": "Electronics", "urdu_name": "الیکٹرانکس", "color": "#3B82F6"},
    {"name": "Clothing", "urdu_name": "لباس", "color": "#EC4899"},
    {"name": "Restaurant", "urdu_name": "ریسٹورنٹ", "color": "#F97316"},
    {"name": "Construction", "urdu_name": "تعمیرات", "color": "#8B5CF6"},
    {"name": "Stationery", "urdu_name": "سٹیشنری", "color": "#14B8A6"},
    {"name": "Other", "urdu_name": "دیگر", "color": "#64748B"},
]

DEFAULT_UNITS = [
    {"name": "Pieces", "code": "pcs", "urdu_name": "ٹکڑے"},
    {"name": "Liter", "code": "ltr", "urdu_name": "لیٹر"},
    {"name": "Milliliter", "code": "ml", "urdu_name": "ملی لیٹر"},
    {"name": "Gram", "code": "g", "urdu_name": "گرام"},
    {"name": "Kilogram", "code": "kg", "urdu_name": "کلوگرام"},
    {"name": "Ton", "code": "ton", "urdu_name": "ٹن"},
    {"name": "Dozen", "code": "dozen", "urdu_name": "درجن"},
    {"name": "Box", "code": "box", "urdu_name": "ڈبہ"},
    {"name": "Meter", "code": "meter", "urdu_name": "میٹر"},
]


def seed_default_categories() -> list[Category]:
    """Seed the 10 standard billing categories idempotently."""
    created_or_found = []
    for item in DEFAULT_CATEGORIES:
        category, _ = Category.objects.get_or_create(
            name=item["name"],
            defaults={
                "urdu_name": item["urdu_name"],
                "color": item["color"],
                "is_archived": False,
            },
        )
        created_or_found.append(category)
    return created_or_found


def seed_default_units() -> list[Unit]:
    """Seed the 9 standard units of measurement idempotently."""
    created_or_found = []
    for item in DEFAULT_UNITS:
        unit, _ = Unit.objects.get_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "urdu_name": item["urdu_name"],
                "is_system": True,
            },
        )
        created_or_found.append(unit)
    return created_or_found
