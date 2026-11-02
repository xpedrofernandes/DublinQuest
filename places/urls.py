# Expose category choices; place and park resource routes come from the project router.
from django.urls import path
from .views import categories

urlpatterns = [path("categories/", categories, name="categories")]
