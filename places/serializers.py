import copy
import json
import math

from collections.abc import Mapping

from django.contrib.gis.geos import GEOSGeometry, Point
from django.contrib.gis.geos.error import GEOSException
from django.contrib.gis.gdal.error import GDALException
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_gis.fields import GeometryField
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from .models import DatasetSource, Park, Place


def reject_unknown(data, allowed):
    """Reject unexpected fields, including attempts to set server-owned values."""
    if not isinstance(data, Mapping):
        raise serializers.ValidationError({"detail": "Expected a JSON object."})
    unknown = set(data) - set(allowed)
    if unknown:
        raise serializers.ValidationError({key: "Unsupported or server-managed field." for key in sorted(unknown)})


class WGS84GeometryField(GeometryField):
    """Accept strict 2D GeoJSON; store metres and return longitude/latitude."""
    def __init__(self, geometry_type, **kwargs):
        self.geometry_type = geometry_type
        super().__init__(transform=4326, **kwargs)

    def to_representation(self, value):
        # The installed DRF GIS transform mutates its input; serialize a copy.
        return super().to_representation(value.clone() if value is not None else value)

    def to_internal_value(self, value):
        if not isinstance(value, dict) or set(value) != {"type", "coordinates"} or value.get("type") != self.geometry_type:
            raise serializers.ValidationError(f"Provide a {self.geometry_type} GeoJSON geometry with type and coordinates only.")

        # Recursion handles both a Point pair and nested MultiPolygon rings.
        def check_coordinates(coordinates):
            if not isinstance(coordinates, list) or not coordinates:
                raise serializers.ValidationError("Coordinates must be nonempty arrays.")
            if isinstance(coordinates[0], list):
                for child in coordinates:
                    check_coordinates(child)
            elif (len(coordinates) != 2 or any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in coordinates)
                    or not -180 <= coordinates[0] <= 180 or not -90 <= coordinates[1] <= 90):
                raise serializers.ValidationError("Use finite [longitude, latitude] pairs in geographic ranges.")
        check_coordinates(value["coordinates"])
        try:
            geometry = GEOSGeometry(json.dumps(value, allow_nan=False), srid=4326)
            if geometry.empty or not geometry.valid:
                raise serializers.ValidationError("Geometry must be nonempty and valid; no automatic repair is performed.")
            # Keep database queries in the projected CRS used by spatial indexes.
            geometry.transform(2157)
        except (GEOSException, GDALException, ValueError, TypeError) as error:
            raise serializers.ValidationError("Invalid GeoJSON geometry.") from error
        if not geometry.valid or not all(math.isfinite(n) for n in geometry.extent):
            raise serializers.ValidationError("Geometry cannot be represented in EPSG:2157.")
        return geometry


class SourceSerializer(serializers.ModelSerializer):
    """Expose dataset attribution alongside imported spatial records."""

    class Meta:
        model = DatasetSource
        fields = ["id", "slug", "title", "publisher", "resource_url", "licence_name", "licence_url", "attribution", "sha256"]


class PlaceSerializer(GeoFeatureModelSerializer):
    point = WGS84GeometryField("Point", read_only=True)
    source = SourceSerializer(read_only=True, allow_null=True)
    distance_m = serializers.SerializerMethodField()

    def get_distance_m(self, obj) -> float | None:
        # Only proximity queries annotate distance; ordinary listings return null.
        distance = getattr(obj, "distance", None)
        return round(distance.m, 2) if distance is not None else None

    class Meta:
        model = Place
        geo_field = "point"
        fields = ["id", "name", "description", "category", "point", "artist", "profile_url", "park", "active", "source", "source_key", "distance_m"]


class ParkSerializer(GeoFeatureModelSerializer):
    boundary = WGS84GeometryField("MultiPolygon", read_only=True)
    source = SourceSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Park
        geo_field = "boundary"
        fields = ["id", "name", "typology", "boundary", "active", "source", "source_key"]


class PlaceWriteSerializer(serializers.ModelSerializer):
    # Provenance, source keys and park links are managed by server-side code.
    point = WGS84GeometryField("Point")

    class Meta:
        model = Place
        fields = ["name", "description", "category", "point", "artist", "profile_url", "active"]

    def to_internal_value(self, data):
        reject_unknown(data, self.fields)
        return super().to_internal_value(data)

    def validate(self, attrs):
        # Merge partial updates into a copy without mutating the live instance.
        candidate = copy.copy(self.instance) if self.instance else Place(source_key="staff:pending")
        for key, value in attrs.items():
            setattr(candidate, key, value)
        if candidate.category == Place.Category.PARK:
            raise serializers.ValidationError({"category": "Manage park representative places through the parks API."})
        try:
            candidate.full_clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict)
        return attrs


class ParkWriteSerializer(serializers.ModelSerializer):
    """Validate writable boundaries; the view synchronizes the park's Place."""

    boundary = WGS84GeometryField("MultiPolygon")

    class Meta:
        model = Park
        fields = ["name", "typology", "boundary", "active"]

    def to_internal_value(self, data):
        reject_unknown(data, self.fields)
        return super().to_internal_value(data)

    def validate(self, attrs):
        # Validate the complete model even when PATCH supplies only some fields.
        candidate = copy.copy(self.instance) if self.instance else Park(source_key="staff:pending")
        for key, value in attrs.items():
            setattr(candidate, key, value)
        try:
            candidate.full_clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict)
        return attrs


class PlaceQuerySerializer(serializers.Serializer):
    categories = serializers.ListField(child=serializers.ChoiceField(choices=Place.Category.choices), required=False, allow_empty=False)
    search = serializers.CharField(required=False, max_length=100, allow_blank=False)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)

    def validate_categories(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Choose distinct categories.")
        return value


class NearbyQuerySerializer(PlaceQuerySerializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    radius_m = serializers.IntegerField(min_value=250, max_value=5000, default=2000)

    def validate(self, attrs):
        if not all(math.isfinite(attrs[key]) for key in ("lat", "lng")):
            raise serializers.ValidationError("Coordinates must be finite.")
        return attrs

    def origin(self):
        # GEOS takes longitude first; EPSG:2157 makes radius comparisons metric.
        origin = Point(self.validated_data["lng"], self.validated_data["lat"], srid=4326)
        try:
            origin.transform(2157)
        except (GDALException, GEOSException) as error:
            raise serializers.ValidationError("Starting point cannot be represented in EPSG:2157.") from error
        if not all(math.isfinite(n) for n in origin.coords):
            raise serializers.ValidationError("Starting point cannot be represented in EPSG:2157.")
        return origin


class ParkQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, max_length=100, allow_blank=False)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)


def validate_query(request, serializer_class):
    # Allow DRF's format option, but reject unknown or repeated filter parameters.
    allowed = {*serializer_class().fields, "format"}
    reject_unknown(request.query_params, allowed)
    data = {}
    for key in request.query_params:
        if len(request.query_params.getlist(key)) != 1:
            raise serializers.ValidationError({key: "Provide each query parameter once."})
        if key != "format":
            data[key] = request.query_params[key]
    if "categories" in data:
        # URL filters use comma-separated text; the serializer expects a list.
        data["categories"] = data["categories"].split(",")
    serializer = serializer_class(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer


class CategorySerializer(serializers.Serializer):
    value = serializers.ChoiceField(choices=Place.Category.choices)
    label = serializers.CharField()
