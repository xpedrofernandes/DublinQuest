# Expose guest-session setup; quest resource routes are registered by the project router.
from django.urls import path
from .views import guest_session

urlpatterns = [path("session/", guest_session, name="guest-session")]
