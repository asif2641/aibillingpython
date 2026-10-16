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
