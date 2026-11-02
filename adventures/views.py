# Handle guest quest requests with owner filtering, CSRF and transactional updates.
import uuid
import time

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.cache import patch_cache_control
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from places.serializers import reject_unknown, validate_query
from .authentication import GuestSessionCSRF
from .generation import generate_adventure
from .models import Adventure, AdventureStop
from .routing import unavailable, walking_route
from .serializers import (
    AdventureInputSerializer, AdventureSerializer, RegenerateSerializer, RenameSerializer,
    SavedQuerySerializer, SessionSerializer, StopProgressSerializer, WalkingRouteSerializer,
)

OWNER_KEY = "adventure_owner"


def guest_owner(request, create=False):
    # Ownership comes from server-side session data, never a request field.
    value = request.session.get(OWNER_KEY)
    if value:
        return uuid.UUID(value)
    if create:
        value = uuid.uuid4()
        request.session[OWNER_KEY] = str(value)
        return value
    return None


@extend_schema(auth=[], responses=SessionSerializer)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def guest_session(request):
    # Establish the guest identity and give the browser a CSRF token for writes.
    guest_owner(request, create=True)
    response = Response({"csrfToken": get_token(request._request)})
    patch_cache_control(response, private=True, no_store=True)
    return response


class AdventurePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


@extend_schema(auth=[], parameters=[OpenApiParameter("X-CSRFToken", str, location=OpenApiParameter.HEADER, description="Required for unsafe methods; obtain from GET /api/session/ in this browser session.")])
@extend_schema_view(partial_update=extend_schema(request=RenameSerializer, responses=AdventureSerializer))
class AdventureViewSet(viewsets.ModelViewSet):
    serializer_class = AdventureSerializer
    permission_classes = [AllowAny]
    authentication_classes = [GuestSessionCSRF]
    pagination_class = AdventurePagination
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Adventure.objects.none()
        # Filter before object lookup so another guest's UUID also returns 404.
        owner = guest_owner(self.request)
        queryset = Adventure.objects.filter(owner_uuid=owner) if owner else Adventure.objects.none()
        if self.action in ("update", "partial_update", "destroy", "regenerate", "stop"):
            # Serialize changes to this quest within the mutation transaction.
            queryset = queryset.select_for_update()
        # Fetch ordered stops and their source details without per-stop queries.
        return queryset.prefetch_related(Prefetch("stops", queryset=AdventureStop.objects.select_related("place__source", "place__park").order_by("position")))

    def get_serializer_class(self):
        if self.action == "create":
            return AdventureInputSerializer
        if self.action in ("update", "partial_update"):
            return RenameSerializer
        return AdventureSerializer

    def finalize_response(self, request, response, *args, **kwargs):
        # Guest-specific responses must not be shared by browser/proxy caches.
        response = super().finalize_response(request, response, *args, **kwargs)
        patch_cache_control(response, private=True, no_store=True)
        return response

    def read(self, adventure):
        # Reload after writes, avoiding stale prefetched stop/progress data.
        return AdventureSerializer(self.get_queryset().get(pk=adventure.pk)).data

    @extend_schema(parameters=[SavedQuerySerializer])
    def list(self, request, *args, **kwargs):
        options = validate_query(request, SavedQuerySerializer).validated_data
        queryset = self.get_queryset()
        if options.get("search"):
            queryset = queryset.filter(title__icontains=options["search"])
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(AdventureSerializer(page, many=True).data)

    def store_generation(self, adventure, values, start):
        # Callers wrap geometry and stop replacement in one atomic transaction.
        generated = generate_adventure(start, values["categories"], values["radius_m"], values["stop_count"])
        adventure.title = values["title"]
        adventure.start = start
        adventure.radius_m = values["radius_m"]
        adventure.categories = values["categories"]
        adventure.requested_stops = values["stop_count"]
        adventure.path, adventure.search_area = generated["path"], generated["search_area"]
        try:
            adventure.full_clean()
            adventure.save()
            # Regeneration replaces the old sequence and its visited timestamps.
            adventure.stops.all().delete()
            for position, stop in enumerate(generated["stops"], 1):
                record = AdventureStop(adventure=adventure, position=position, **stop)
                record.full_clean()
                record.save()
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict)
        return adventure

    @extend_schema(request=AdventureInputSerializer, responses={201: AdventureSerializer})
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = AdventureInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        adventure = Adventure(owner_uuid=guest_owner(request, create=True))
        self.store_generation(adventure, serializer.validated_data, serializer.projected_start)
        return Response(self.read(adventure), status=201)

    @extend_schema(request=RenameSerializer, responses=AdventureSerializer)
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        adventure = self.get_object()
        serializer = RenameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        adventure.title = serializer.validated_data["title"]
        adventure.full_clean()
        adventure.save(update_fields=["title", "updated_at"])
        return Response(self.read(adventure))

    @extend_schema(request=RegenerateSerializer, responses=AdventureSerializer)
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def regenerate(self, request, **kwargs):
        adventure = self.get_object()
        reject_unknown(request.data, RegenerateSerializer().fields)
        start = adventure.start.clone()
        geographic = start.clone()
        geographic.transform(4326)
        # Merge edits with saved criteria so omitted fields retain their values.
        defaults = {"title": adventure.title, "lat": geographic.y, "lng": geographic.x,
            "radius_m": adventure.radius_m, "categories": adventure.categories,
            "stop_count": adventure.requested_stops}
        serializer = RegenerateSerializer(data={**defaults, **request.data})
        serializer.is_valid(raise_exception=True)
        if adventure.stops.filter(visited_at__isnull=False).exists() and not serializer.validated_data["confirm_reset"]:
            raise serializers.ValidationError({"confirm_reset": "Regeneration resets visited progress; set confirm_reset to true to continue."})
        if "lat" in request.data or "lng" in request.data:
            start = serializer.projected_start
        self.store_generation(adventure, serializer.validated_data, start)
        return Response(self.read(adventure))

    @extend_schema(request=StopProgressSerializer, responses=AdventureSerializer)
    @action(detail=True, methods=["patch"], url_path=r"stops/(?P<stop_id>\d+)")
    @transaction.atomic
    def stop(self, request, stop_id=None, **kwargs):
        adventure = self.get_object()
        serializer = StopProgressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        stop = get_object_or_404(adventure.stops, pk=stop_id)
        # Repeated visited updates retain the original self-reported timestamp.
        if serializer.validated_data["visited"]:
            if stop.visited_at is None:
                stop.visited_at = timezone.now()
        else:
            stop.visited_at = None
        stop.save(update_fields=["visited_at"])
        adventure.save(update_fields=["updated_at"])
        return Response(self.read(adventure))

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        self.get_object().delete()
        return Response(status=204)

    @extend_schema(request=None, responses=WalkingRouteSerializer)
    @action(detail=True, methods=["post"], url_path="walking-route")
    def walking_route(self, request, **kwargs):
        adventure = self.get_object()  # Ownership checked before contacting ORS.
        reject_unknown(request.data, [])
        stops = list(adventure.stops.all())
        if not adventure.path or len(adventure.path.coords) != len(stops) + 1:
            return Response(unavailable("Regenerate this adventure before requesting a walking route."))
        # A staff edit may have moved a source place since this path was generated.
        if any(abs(stop.place.point.x - xy[0]) > .001 or abs(stop.place.point.y - xy[1]) > .001
                for stop, xy in zip(stops, adventure.path.coords[1:])):
            return Response(unavailable("An attraction has moved in the data; regenerate the adventure first."))
        # Limit provider requests per session; frontend progress uses cached routes.
        now = time.time()
        if now - request.session.get("walking_route_requested_at", 0) < 30:
            return Response(unavailable("Please wait 30 seconds between walking-route requests."))
        request.session["walking_route_requested_at"] = now
        return Response(walking_route(adventure.path))
