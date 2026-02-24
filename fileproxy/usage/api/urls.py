from django.urls import path

from .views import UsageViewSet

urlpatterns = [
    path(
        "usage/summary/",
        UsageViewSet.as_view({"get": "summary"}),
        name="usage-summary",
    ),
    path(
        "usage/by-vault/",
        UsageViewSet.as_view({"get": "by_vault"}),
        name="usage-by-vault",
    ),
    path(
        "usage/timeline/",
        UsageViewSet.as_view({"get": "timeline"}),
        name="usage-timeline",
    ),
]
