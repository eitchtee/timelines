from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"

    def ready(self):
        from django.contrib import admin
        from django.contrib.sites.models import Site

        # django.contrib.sites is only installed because allauth and the sitemap
        # framework expect it; a single-tenant project has nothing to edit here.
        admin.site.unregister(Site)

        from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken

        # Providers are configured from the environment, not the database.
        admin.site.unregister(SocialAccount)
        admin.site.unregister(SocialApp)
        admin.site.unregister(SocialToken)

        # Registers the environment system checks as a side effect.
        from apps.common import checks  # noqa: F401
