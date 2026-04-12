from django.urls import path

from . import views
from .ui import views as ui_views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("beta/", views.beta_signup, name="beta-signup"),
    path("beta/pending/", views.beta_pending, name="beta-pending"),
    path("profile/", ui_views.profile, name="profile"),
]
