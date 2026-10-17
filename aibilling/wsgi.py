"""
aibilling/wsgi.py
==================
WSGI config for the aibilling project.

WSGI (Web Server Gateway Interface) is the standard interface between
web servers (like Gunicorn or Nginx) and Python web applications.

In production, Gunicorn reads this file to serve the app:
    gunicorn aibilling.wsgi:application

https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os
import sys
from pathlib import Path

from django.core.wsgi import get_wsgi_application

# Ensure project root is on sys.path for Vercel and serverless lambdas
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Use production settings if on Vercel or in production, else local
default_settings = (
    "aibilling.settings.production" if os.environ.get("VERCEL") else "aibilling.settings.local"
)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", default_settings)

application = get_wsgi_application()
app = application

# Auto-apply database migrations and seed administrative users on Vercel boot
if os.environ.get("VERCEL"):
    try:
        from django.core.management import call_command

        call_command("migrate", interactive=False)
    except Exception as _migrate_exc:  # noqa: S110
        import logging

        logging.getLogger(__name__).warning("Startup migration failed or skipped: %s", _migrate_exc)

    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        admin_pass = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "AdminPass123!")

        # Guarantee 'superadmin' user exists and has superuser privileges
        superadmin_u = User.objects.filter(username="superadmin").first()
        if not superadmin_u:
            User.objects.create_superuser(
                username="superadmin",
                email="admin@scanbooks.local",
                password=admin_pass,
            )
        elif not superadmin_u.check_password(admin_pass) or not superadmin_u.is_superuser:
            superadmin_u.set_password(admin_pass)
            superadmin_u.is_superuser = True
            superadmin_u.is_staff = True
            superadmin_u.is_active = True
            superadmin_u.is_locked = False
            superadmin_u.failed_login_attempts = 0
            superadmin_u.locked_until = None
            superadmin_u.save()

        # Guarantee 'admin' user also has valid credentials
        admin_u = User.objects.filter(username="admin").first()
        if admin_u and not (admin_u.check_password("admin") or admin_u.check_password(admin_pass)):
            admin_u.set_password("admin")
            admin_u.is_superuser = True
            admin_u.is_staff = True
            admin_u.is_active = True
            admin_u.is_locked = False
            admin_u.failed_login_attempts = 0
            admin_u.locked_until = None
            admin_u.save()

        from accounts.services import register_owner_user

        demo_u = User.objects.filter(username="demo").first()
        if not demo_u:
            register_owner_user(
                username="demo",
                password="demo",
                business_name="Demo Business",
                email="demo@example.com",
                plan=User.Plan.PRO,
            )
        elif not (demo_u.check_password("demo") or demo_u.check_password("DemoPass123!")):
            demo_u.set_password("demo")
            demo_u.is_active = True
            demo_u.is_locked = False
            demo_u.failed_login_attempts = 0
            demo_u.locked_until = None
            demo_u.save()

        demo1_u = User.objects.filter(username="demo1").first()
        if not demo1_u:
            register_owner_user(
                username="demo1",
                password="demo1",
                business_name="demo1",
                email="demo1@example.com",
                plan=User.Plan.FREE,
            )
        elif not (demo1_u.check_password("demo1") or demo1_u.check_password("DemoPass123!")):
            demo1_u.set_password("demo1")
            demo1_u.is_active = True
            demo1_u.is_locked = False
            demo1_u.failed_login_attempts = 0
            demo1_u.locked_until = None
            demo1_u.save()
    except Exception as _seed_exc:  # noqa: S110
        import logging

        logging.getLogger(__name__).warning("Initial user seed failed or skipped: %s", _seed_exc)
