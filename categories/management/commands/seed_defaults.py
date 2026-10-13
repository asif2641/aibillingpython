"""
categories/management/commands/seed_defaults.py
===============================================
Management command to seed both categories and units.
"""

from django.core.management.base import BaseCommand

from categories.services import seed_default_categories, seed_default_units


class Command(BaseCommand):
    help = "Seed default categories and measurement units."

    def handle(self, *args, **options):
        cats = seed_default_categories()
        units = seed_default_units()
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully seeded {len(cats)} categories and {len(units)} units."
            )
        )
