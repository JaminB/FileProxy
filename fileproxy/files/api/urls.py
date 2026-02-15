from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import FilesViewSet

router = DefaultRouter()
router.register(r"files", FilesViewSet, basename="files")

urlpatterns = [
    path("", include(router.urls)),
]
