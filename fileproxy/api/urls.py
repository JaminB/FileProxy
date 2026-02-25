from django.urls import include, path

urlpatterns = [
    path("", include("vault.api.urls")),
    path("", include("files.api.urls")),
    path("", include("usage.api.urls")),
    path("", include("subscription.api.urls")),
]
