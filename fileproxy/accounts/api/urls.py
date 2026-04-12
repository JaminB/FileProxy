from rest_framework.routers import DefaultRouter

from .views import APIKeyViewSet, UserViewSet

router = DefaultRouter()
router.register(r"accounts/api-keys", APIKeyViewSet, basename="api-key")
router.register(r"users", UserViewSet, basename="user")

urlpatterns = router.urls
