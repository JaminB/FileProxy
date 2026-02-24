from django.urls import path

from . import views

app_name = "usage_ui"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("vault/<str:name>/", views.vault_detail, name="vault_detail"),
]
