from django.urls import path
from .views import guest_session

urlpatterns = [path("session/", guest_session, name="guest-session")]
