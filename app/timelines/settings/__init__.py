"""Settings package.

``DJANGO_SETTINGS_MODULE`` points at one of the concrete modules:

* ``timelines.settings.dev``  -- local development
* ``timelines.settings.prod`` -- production

Both build on ``base``. Nothing should import from this ``__init__``.
"""
