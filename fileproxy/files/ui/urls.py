from __future__ import annotations

from django.urls import path

from .browse import browse

urlpatterns = [
    path("", browse, name="files_browse"),
]
