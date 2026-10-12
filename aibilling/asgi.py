"""
aibilling/asgi.py
==================
ASGI config for the aibilling project.

ASGI (Asynchronous Server Gateway Interface) is the modern successor to WSGI.
It supports both synchronous and asynchronous request handling.

This is included for future use (e.g., Django Channels for WebSockets).
Currently the app uses standard synchronous Django views.

https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

# Use the local settings by default; production overrides this via the environment.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aibilling.settings.local")

application = get_asgi_application()
