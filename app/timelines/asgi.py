"""ASGI config for Timelines."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", "timelines.settings.prod"
)

application = get_asgi_application()
