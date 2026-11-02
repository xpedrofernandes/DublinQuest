from django.apps import AppConfig


class PlacesConfig(AppConfig):
    """Register the spatial-data app and its default primary-key type."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "places"
