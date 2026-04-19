from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.http import HttpResponsePermanentRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.urls import include, path
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def health(request):
    return JsonResponse({"status": "ok"})


def index(request):
    if request.user.is_authenticated:
        return redirect("home")
    return render(request, "landing.html")


urlpatterns = [
    path("health/", health, name="health"),
    path("", index, name="index"),
    path("home/", login_required(TemplateView.as_view(template_name="home.html")), name="home"),
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
    path("admin-panel/", include("admin_panel.urls")),
    path("users/", lambda req: HttpResponsePermanentRedirect("/admin-panel/users/")),
    path("users/<int:user_id>/", lambda req, user_id: HttpResponsePermanentRedirect(f"/admin-panel/users/{user_id}/")),
    path("admin/", admin.site.urls),
    path("files/", include("files.ui.urls")),
    path("connections/", include("connections.ui.urls")),
    path("usage/", include("usage.ui.urls")),
    path("subscription/", include("subscription.ui.urls")),
    path("api/v1/", include("api.urls")),
    path(
        "clients/",
        login_required(TemplateView.as_view(template_name="clients/index.html")),
        name="clients",
    ),
    path(
        "clients/windows-explorer/",
        login_required(TemplateView.as_view(template_name="clients/windows_explorer.html")),
        name="clients-windows-explorer",
    ),
]
