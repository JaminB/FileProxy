from django.urls import include, path

urlpatterns = [
    path("", include("connections.api.urls")),
    path("", include("files.api.urls")),
    path("", include("usage.api.urls")),
    path("", include("subscription.api.urls")),
]
