"""
accounts/management/commands/create_superadmin.py
===================================================
Management command to create a Super Admin user for development.

Run with:
    python manage.py create_superadmin

This command is safe to run multiple times — it will not create a
duplicate if a user with the given username already exists.

In production, use `python manage.py createsuperuser` instead,
which prompts for a password interactively.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Create a default Super Admin account for development.

    Creates user 'admin' with password 'admin' if it does not exist.
    Only use this in local development — not in production.
    """

    help = "Create a default superadmin account for development (username: admin, password: admin)"

    def handle(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        """Execute the command."""
        User = get_user_model()
        username = "admin"
        password = "admin"  # noqa: S105

        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(f"User '{username}' already exists. No changes made.")
            )
            return

        User.objects.create_superuser(
            username=username,
            email="admin@example.com",
            password=password,
            role=User.Role.SUPERADMIN,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Super Admin created successfully!\n"
                f"  Username: {username}\n"
                f"  Password: {password}\n"
                f"  WARNING: Change this password immediately in production!"
            )
        )
