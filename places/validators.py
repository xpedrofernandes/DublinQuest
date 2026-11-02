# Enforce nonempty, valid EPSG:2157 geometry before application code saves it.
from django.core.exceptions import ValidationError


def validate_geometry(value):
    """Reject empty/invalid geometry; transform source coordinates before saving."""
    if value.empty or not value.valid:
        raise ValidationError("Geometry must be nonempty and valid.")
    if value.srid != 2157:
        raise ValidationError("Geometry must be transformed to EPSG:2157.")
