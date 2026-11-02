from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ParkViewSet, PlaceViewSet, categories

router = DefaultRouter()
router.register("places", PlaceViewSet)
router.register("parks", ParkViewSet)
urlpatterns = [path("categories/", categories, name="categories"), path("", include(router.urls))]
