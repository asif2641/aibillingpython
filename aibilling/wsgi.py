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

from django.core.wsgi import get_wsgi_application

# Use the local settings by default; production overrides this via the environment.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aibilling.settings.local")

application = get_wsgi_application()
app = application
