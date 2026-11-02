import uuid

from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator

from places.models import Place
from places.validators import validate_geometry


class Adventure(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_uuid = models.UUIDField(db_index=True, editable=False)
    title = models.CharField(max_length=120)
    start = models.PointField(srid=2157, spatial_index=True, validators=[validate_geometry])
    radius_m = models.PositiveIntegerField(default=2000, validators=[MinValueValidator(250), MaxValueValidator(5000)])
    categories = models.JSONField(default=list)
    requested_stops = models.PositiveSmallIntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(10)])
    # Filled by adventure generation later; NULL distinguishes an ungenerated record.
    search_area = models.PolygonField(srid=2157, spatial_index=True, null=True, blank=True, validators=[validate_geometry])
    path = models.LineStringField(srid=2157, spatial_index=True, null=True, blank=True, validators=[validate_geometry])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(radius_m__gte=250, radius_m__lte=5000), name="adventure_radius_range"),
            models.CheckConstraint(condition=models.Q(requested_stops__gte=1, requested_stops__lte=10), name="adventure_stop_count_range"),
        ]

    def clean(self):
        super().clean()
        if (not isinstance(self.categories, list) or not self.categories
                or any(not isinstance(item, str) or item not in Place.Category.values for item in self.categories)
                or len(set(self.categories)) != len(self.categories)):
            raise ValidationError({"categories": "Choose at least one distinct supported category."})

    def __str__(self):
        return self.title


class AdventureStop(models.Model):
    adventure = models.ForeignKey(Adventure, on_delete=models.CASCADE, related_name="stops")
    place = models.ForeignKey(Place, on_delete=models.PROTECT, related_name="adventure_stops")
    position = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    distance_from_start_m = models.FloatField(validators=[MinValueValidator(0)])
    distance_from_previous_m = models.FloatField(validators=[MinValueValidator(0)])
    visited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["adventure", "position"], name="stop_position_unique"),
            models.UniqueConstraint(fields=["adventure", "place"], name="stop_place_unique"),
            models.CheckConstraint(condition=models.Q(position__gte=1), name="stop_position_positive"),
            models.CheckConstraint(condition=models.Q(distance_from_start_m__gte=0, distance_from_previous_m__gte=0), name="stop_distances_nonnegative"),
        ]
