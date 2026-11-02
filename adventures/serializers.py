from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from places.models import Place
from places.serializers import NearbyQuerySerializer, PlaceSerializer, WGS84GeometryField, reject_unknown
from .generation import SEQUENCE_NOTICE
from .models import Adventure, AdventureStop


class AdventureInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=120, default="Dublin adventure")
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    categories = serializers.ListField(child=serializers.ChoiceField(choices=Place.Category.choices), min_length=1, max_length=4)
    radius_m = serializers.IntegerField(min_value=250, max_value=5000, default=2000)
    stop_count = serializers.IntegerField(min_value=1, max_value=10, default=5)

    def to_internal_value(self, data):
        reject_unknown(data, self.fields)
        for key in ("lat", "lng", "radius_m", "stop_count"):
            if isinstance(data.get(key), bool):
                raise serializers.ValidationError({key: "Provide a number, not a boolean."})
        return super().to_internal_value(data)

    def validate_categories(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Choose distinct categories.")
        return sorted(value)

    def validate(self, attrs):
        # Reuse the spatial API's finite/range/transformation checks.
        query = NearbyQuerySerializer(data={key: attrs[key] for key in ("lat", "lng", "radius_m")})
        query.is_valid(raise_exception=True)
        self.projected_start = query.origin()
        return attrs


class RegenerateSerializer(AdventureInputSerializer):
    lat = serializers.FloatField(min_value=-90, max_value=90, required=False)
    lng = serializers.FloatField(min_value=-180, max_value=180, required=False)
    categories = serializers.ListField(child=serializers.ChoiceField(choices=Place.Category.choices), min_length=1, max_length=4, required=False)
    confirm_reset = serializers.BooleanField(default=False)


class RenameSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=120)

    def to_internal_value(self, data):
        reject_unknown(data, self.fields)
        return super().to_internal_value(data)


class StopProgressSerializer(serializers.Serializer):
    visited = serializers.BooleanField()

    def to_internal_value(self, data):
        reject_unknown(data, self.fields)
        return super().to_internal_value(data)


class AdventureStopSerializer(serializers.ModelSerializer):
    place = PlaceSerializer(read_only=True)
    visited = serializers.SerializerMethodField()

    def get_visited(self, obj) -> bool:
        return obj.visited_at is not None

    class Meta:
        model = AdventureStop
        fields = ["id", "position", "place", "distance_from_start_m", "distance_from_previous_m", "visited", "visited_at"]


class ProgressSerializer(serializers.Serializer):
    visited = serializers.IntegerField()
    total = serializers.IntegerField()
    percent = serializers.FloatField()
    complete = serializers.BooleanField()


class AdventureSerializer(serializers.ModelSerializer):
    start = WGS84GeometryField("Point", read_only=True)
    search_area = WGS84GeometryField("Polygon", read_only=True)
    path = WGS84GeometryField("LineString", read_only=True)
    stops = AdventureStopSerializer(many=True, read_only=True)
    progress = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()
    total_distance_m = serializers.SerializerMethodField()
    sequence_notice = serializers.SerializerMethodField()

    @extend_schema_field(ProgressSerializer)
    def get_progress(self, obj) -> dict:
        stops = list(obj.stops.all())
        visited = sum(stop.visited_at is not None for stop in stops)
        return {"visited": visited, "total": len(stops),
            "percent": round(100 * visited / len(stops), 2) if stops else 0,
            "complete": bool(stops) and visited == len(stops)}

    def get_warnings(self, obj) -> list[str]:
        count = len(obj.stops.all())
        return [f"Only {count} distinct eligible locations were available; {obj.requested_stops} were requested."] if count < obj.requested_stops else []

    def get_total_distance_m(self, obj) -> float:
        return round(sum(stop.distance_from_previous_m for stop in obj.stops.all()), 2)

    def get_sequence_notice(self, obj) -> str:
        return SEQUENCE_NOTICE

    class Meta:
        model = Adventure
        fields = ["id", "title", "start", "radius_m", "categories", "requested_stops", "search_area", "path",
            "stops", "progress", "warnings", "total_distance_m", "sequence_notice", "created_at", "updated_at"]


class SavedQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=50)
    search = serializers.CharField(required=False, max_length=100, allow_blank=False)


class SessionSerializer(serializers.Serializer):
    csrfToken = serializers.CharField()
