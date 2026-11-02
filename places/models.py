from django.contrib.gis.db import models
from django.core.validators import RegexValidator

from .validators import validate_geometry


class DatasetSource(models.Model):
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=255)
    publisher = models.CharField(max_length=255)
    resource_url = models.URLField(max_length=1000)
    licence_name = models.CharField(max_length=255)
    licence_url = models.URLField(max_length=1000)
    attribution = models.TextField()
    snapshot_filename = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64, validators=[RegexValidator(r"\A[0-9a-f]{64}\Z")])

    def __str__(self):
        return self.title


class Park(models.Model):
    source = models.ForeignKey(DatasetSource, on_delete=models.PROTECT, null=True, blank=True)
    source_key = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    typology = models.CharField(max_length=100, blank=True)
    boundary = models.MultiPolygonField(srid=2157, spatial_index=True, validators=[validate_geometry])
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "source_key"], name="park_source_key_unique")]
        ordering = ["name", "pk"]

    def __str__(self):
        return self.name


class Place(models.Model):
    class Category(models.TextChoices):
        STREET_ART = "street_art", "Street art"
        PUBLIC_ART = "public_art", "Public art and memorials"
        HERITAGE = "heritage", "Heritage and landmarks"
        PARK = "park", "Parks"

    source = models.ForeignKey(DatasetSource, on_delete=models.PROTECT, null=True, blank=True)
    source_key = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, db_index=True)
    point = models.PointField(srid=2157, spatial_index=True, validators=[validate_geometry])
    artist = models.CharField(max_length=255, blank=True)
    profile_url = models.URLField(max_length=1000, blank=True)
    park = models.OneToOneField(Park, on_delete=models.CASCADE, null=True, blank=True, related_name="place")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "source_key"], name="place_source_key_unique"),
            models.CheckConstraint(condition=models.Q(category__in=["street_art", "public_art", "heritage", "park"]), name="place_category_valid"),
            models.CheckConstraint(condition=(models.Q(category="park", park__isnull=False) | (~models.Q(category="park") & models.Q(park__isnull=True))), name="place_park_category_consistent"),
        ]
        ordering = ["name", "pk"]

    def __str__(self):
        return self.name
