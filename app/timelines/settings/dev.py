"""Development settings.

Adds the debug toolbar and the browser-reload middleware, and points the
templates at Vite's dev server instead of the built manifest.
"""

import os
import socket

from .base import *  # noqa: F401,F403
from .base import INSTALLED_APPS, MIDDLEWARE, env_bool

DEBUG = env_bool("DEBUG", True)

SECRET_KEY = os.getenv("SECRET_KEY", "insecure-development-key")

# Vite serves assets straight from memory in development; there is no manifest
# to read until ``npm run build`` has run.
DJANGO_VITE_DEV_MODE = env_bool("DJANGO_VITE_DEV_MODE", True)

INSTALLED_APPS = [
    "django_browser_reload",
    "debug_toolbar",
    *INSTALLED_APPS,
]

MIDDLEWARE = [
    "django_browser_reload.middleware.BrowserReloadMiddleware",
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    *MIDDLEWARE,
]

# ``hx-preserve`` keeps the toolbar alive across htmx swaps.
DEBUG_TOOLBAR_CONFIG = {"ROOT_TAG_EXTRA_ATTRS": "hx-preserve"}

INTERNAL_IPS = ["127.0.0.1"]

if DEBUG:
    # Docker gives the container an arbitrary IP; the toolbar only renders for
    # addresses in INTERNAL_IPS, so add the gateway of every local interface.
    _hostname, _, _ips = socket.gethostbyname_ex(socket.gethostname())
    INTERNAL_IPS += [".".join(ip.split(".")[:-1] + ["1"]) for ip in _ips]
    try:
        _, _, _node_ips = socket.gethostbyname_ex("node")
    except socket.gaierror:
        # The vite container isn't up (yet?).
        pass
    else:
        INTERNAL_IPS.extend(_node_ips)

# Serve static files straight from STATICFILES_DIRS in dev without collectstatic.
WHITENOISE_USE_FINDERS = True
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
