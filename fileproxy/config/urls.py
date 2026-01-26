from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("vault/", include("vault.ui.urls")),
    path("api/v1/", include("vault.api.urls")), 
]
