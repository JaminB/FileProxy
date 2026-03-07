from django.urls import path

from . import views
from .ui import views as ui_views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("profile/", ui_views.profile, name="profile"),
]
