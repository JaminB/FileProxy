from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ConnectionViewSet

router = DefaultRouter()
router.register(r"connections", ConnectionViewSet, basename="connection")


urlpatterns = [
    path("", include(router.urls)),
]
