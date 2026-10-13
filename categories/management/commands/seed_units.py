"""
categories/management/commands/seed_units.py
============================================
Management command to seed standard measurement units.
"""

from django.core.management.base import BaseCommand

from categories.services import seed_default_units


class Command(BaseCommand):
    help = "Seed standard measurement units."

    def handle(self, *args, **options):
        units = seed_default_units()
        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(units)} units."))
