#!/usr/bin/env python
"""
manage.py
==========
Django's command-line utility for administrative tasks.

Usage examples:
    python manage.py runserver          # Start the development server
    python manage.py makemigrations     # Create new database migrations
    python manage.py migrate            # Apply pending migrations
    python manage.py createsuperuser    # Create an admin account
    python manage.py shell              # Open an interactive Python shell

https://docs.djangoproject.com/en/4.2/ref/django-admin/
"""

import os
import sys


def main() -> None:
    """Run administrative tasks."""
    # Use the local (development) settings by default.
    # On a production server, set the DJANGO_SETTINGS_MODULE environment variable
    # to "aibilling.settings.production" before running this script.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aibilling.settings.local")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
