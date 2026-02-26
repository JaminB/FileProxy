from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import include, path
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("", login_required(TemplateView.as_view(template_name="home.html")), name="home"),
    path(
        "docs/",
        login_required(TemplateView.as_view(template_name="api_docs.html")),
        name="api-docs-embed",
    ),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("accounts/", include("django.contrib.auth.urls")),
    path("accounts/", include("accounts.urls")),
    path("admin/", admin.site.urls),
    path("files/", include("files.ui.urls")),
    path("connections/", include("connections.ui.urls")),
    path("usage/", include("usage.ui.urls")),
    path("subscription/", include("subscription.ui.urls")),
    path("api/v1/", include("api.urls")),
]
