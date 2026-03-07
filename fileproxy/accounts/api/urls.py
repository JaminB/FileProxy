from rest_framework.routers import DefaultRouter

from .views import APIKeyViewSet

router = DefaultRouter()
router.register(r"accounts/api-keys", APIKeyViewSet, basename="api-key")

urlpatterns = router.urls
