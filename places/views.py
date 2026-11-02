import json
import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from .models import Park, Place
from .pagination import GeoJSONPagination
from .permissions import StaffWriteOrReadOnly
from .serializers import (
    CategorySerializer, NearbyQuerySerializer, ParkQuerySerializer, ParkSerializer, ParkWriteSerializer,
    PlaceQuerySerializer, PlaceSerializer, PlaceWriteSerializer, validate_query,
)
from .spatial import buffered_search_area, contained_places, intersecting_parks, nearby_places


@extend_schema_view(partial_update=extend_schema(request=PlaceWriteSerializer, responses=PlaceSerializer))
class PlaceViewSet(viewsets.ModelViewSet):
    queryset = Place.objects.select_related("source", "park").all()
    serializer_class = PlaceSerializer
    pagination_class = GeoJSONPagination
    permission_classes = [StaffWriteOrReadOnly]
    authentication_classes = [SessionAuthentication]
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return PlaceWriteSerializer
        return PlaceSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if not (self.request.user.is_authenticated and self.request.user.is_staff):
            queryset = queryset.filter(active=True)
            # Hide representative points of inactive parks as well.
            queryset = queryset.exclude(park__active=False)
        return queryset

    def filtered_places(self, options):
        queryset = self.get_queryset()
        if options.get("categories"):
            queryset = queryset.filter(category__in=options["categories"])
        if options.get("search"):
            queryset = queryset.filter(name__icontains=options["search"])
        return queryset

    @extend_schema(parameters=[PlaceQuerySerializer])
    def list(self, request, *args, **kwargs):
        options = validate_query(request, PlaceQuerySerializer).validated_data
        return self.collection(self.filtered_places(options))

    def collection(self, queryset):
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @extend_schema(parameters=[NearbyQuerySerializer], responses=PlaceSerializer(many=True))
    @action(detail=False, methods=["get"])
    def nearby(self, request, **kwargs):
        query = validate_query(request, NearbyQuerySerializer)
        queryset = nearby_places(self.filtered_places(query.validated_data), query.origin(), query.validated_data["radius_m"])
        return self.collection(queryset)

    @extend_schema(request=PlaceWriteSerializer, responses={201: PlaceSerializer})
    def create(self, request, *args, **kwargs):
        return self.write(request)

    @extend_schema(request=PlaceWriteSerializer, responses=PlaceSerializer)
    def update(self, request, *args, **kwargs):
        return self.write(request, self.get_object(), partial=kwargs.get("partial", False))

    @transaction.atomic
    def write(self, request, instance=None, partial=False):
        if instance and instance.park_id:
            raise serializers.ValidationError({"detail": "Manage park representative places through the parks API."})
        serializer = PlaceWriteSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        extra = {"source_key": f"staff:{uuid.uuid4()}"} if instance is None else {}
        obj = serializer.save(**extra)
        return Response(PlaceSerializer(obj).data, status=status.HTTP_201_CREATED if instance is None else status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.park_id:
            raise serializers.ValidationError({"detail": "Delete the park through the parks API."})
        try:
            with transaction.atomic():
                obj.delete()
        except ProtectedError:
            return Response({"detail": "This place is used by a saved adventure."}, status=409)
        return Response(status=204)


@extend_schema_view(partial_update=extend_schema(request=ParkWriteSerializer, responses=ParkSerializer))
class ParkViewSet(viewsets.ModelViewSet):
    queryset = Park.objects.select_related("source").all()
    serializer_class = ParkSerializer
    pagination_class = GeoJSONPagination
    permission_classes = [StaffWriteOrReadOnly]
    authentication_classes = [SessionAuthentication]
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ParkWriteSerializer
        return ParkSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if not (self.request.user.is_authenticated and self.request.user.is_staff):
            queryset = queryset.filter(active=True)
        return queryset

    @extend_schema(parameters=[ParkQuerySerializer])
    def list(self, request, *args, **kwargs):
        options = validate_query(request, ParkQuerySerializer).validated_data
        queryset = self.get_queryset()
        if options.get("search"):
            queryset = queryset.filter(name__icontains=options["search"])
        return self.collection(queryset)

    def collection(self, queryset):
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @extend_schema(parameters=[PlaceQuerySerializer], responses=PlaceSerializer(many=True))
    @action(detail=True, methods=["get"])
    def places(self, request, pk=None, **kwargs):
        park = self.get_object()
        options = validate_query(request, PlaceQuerySerializer).validated_data
        queryset = Place.objects.filter(active=True).exclude(category="park").select_related("source", "park")
        if options.get("categories"):
            queryset = queryset.filter(category__in=options["categories"])
        if options.get("search"):
            queryset = queryset.filter(name__icontains=options["search"])
        queryset = contained_places(queryset, park)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(PlaceSerializer(page, many=True).data)

    @extend_schema(parameters=[NearbyQuerySerializer], responses=ParkSerializer(many=True))
    @action(detail=False, methods=["get"])
    def intersecting(self, request, **kwargs):
        query = validate_query(request, NearbyQuerySerializer)
        # Categories apply to point searches, not to park intersection requests.
        if "categories" in query.validated_data:
            raise serializers.ValidationError({"categories": "Not applicable to park intersection searches."})
        area = buffered_search_area(query.origin(), query.validated_data["radius_m"])
        queryset = self.get_queryset()
        if query.validated_data.get("search"):
            queryset = queryset.filter(name__icontains=query.validated_data["search"])
        response = self.collection(intersecting_parks(queryset, area))
        area.transform(4326)
        response.data["search_area"] = json.loads(area.geojson)
        return response

    @extend_schema(request=ParkWriteSerializer, responses={201: ParkSerializer})
    def create(self, request, *args, **kwargs):
        return self.write(request)

    @extend_schema(request=ParkWriteSerializer, responses=ParkSerializer)
    def update(self, request, *args, **kwargs):
        return self.write(request, self.get_object(), partial=kwargs.get("partial", False))

    @transaction.atomic
    def write(self, request, instance=None, partial=False):
        serializer = ParkWriteSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        extra = {"source_key": f"staff:{uuid.uuid4()}"} if instance is None else {}
        park = serializer.save(**extra)
        place = Place.objects.filter(park=park).first()
        if place is None:
            place = Place(park=park, source=park.source, source_key=park.source_key, category="park",
                description="Representative point within the park boundary; not a verified entrance.")
        place.name, place.active = park.name, park.active
        place.point = park.boundary.point_on_surface
        try:
            place.full_clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict)
        place.save()
        return Response(ParkSerializer(park).data, status=201 if instance is None else 200)

    def destroy(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                self.get_object().delete()
        except ProtectedError:
            return Response({"detail": "This park's representative place is used by a saved adventure."}, status=409)
        return Response(status=204)


@extend_schema(responses=CategorySerializer(many=True))
@api_view(["GET"])
def categories(request):
    return Response([{"value": value, "label": label} for value, label in Place.Category.choices])
