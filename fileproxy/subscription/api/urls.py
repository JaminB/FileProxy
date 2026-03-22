from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (MyAvailablePlansView, MySubscriptionCancelView,
                    MySubscriptionSwitchView, MySubscriptionUsageView,
                    MySubscriptionView, SubscriptionPlanViewSet)

router = DefaultRouter()
router.register("subscription/plans", SubscriptionPlanViewSet, basename="subscription-plan")

urlpatterns = router.urls + [
    path("subscription/my/", MySubscriptionView.as_view(), name="my-subscription"),
    path(
        "subscription/my/switch/", MySubscriptionSwitchView.as_view(), name="my-subscription-switch"
    ),
    path(
        "subscription/my/cancel/", MySubscriptionCancelView.as_view(), name="my-subscription-cancel"
    ),
    path("subscription/my/usage/", MySubscriptionUsageView.as_view(), name="my-subscription-usage"),
    path("subscription/my/plans/", MyAvailablePlansView.as_view(), name="my-available-plans"),
]
