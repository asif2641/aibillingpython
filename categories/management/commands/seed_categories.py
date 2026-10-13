"""
categories/management/commands/seed_categories.py
=================================================
Management command to seed default billing categories.
"""

from django.core.management.base import BaseCommand

from categories.services import seed_default_categories


class Command(BaseCommand):
    help = "Seed standard billing categories."

    def handle(self, *args, **options):
        cats = seed_default_categories()
        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(cats)} categories."))
