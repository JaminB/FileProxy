from django.urls import path

from .views import UsageViewSet

urlpatterns = [
    path(
        "usage/summary/",
        UsageViewSet.as_view({"get": "summary"}),
        name="usage-summary",
    ),
    path(
        "usage/by-connection/",
        UsageViewSet.as_view({"get": "by_connection"}),
        name="usage-by-connection",
    ),
    path(
        "usage/timeline/",
        UsageViewSet.as_view({"get": "timeline"}),
        name="usage-timeline",
    ),
]
