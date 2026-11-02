from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from adventures.views import AdventureViewSet
from places.views import ParkViewSet, PlaceViewSet

from .views import explore, health

router = DefaultRouter()
router.register("places", PlaceViewSet)
router.register("parks", ParkViewSet)
router.register("adventures", AdventureViewSet, basename="adventure")

urlpatterns = [
    path("", explore, name="explore"),
    path("api/", include("adventures.urls")),
    path("api/", include("places.urls")),
    path("api/", include(router.urls)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api-auth/", include("rest_framework.urls")),
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
]
