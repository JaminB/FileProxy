from django.urls import path

from . import views

app_name = "usage_ui"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("vault/", views.vault_metrics, name="vault_metrics"),
]
