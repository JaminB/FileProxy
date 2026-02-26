from django.urls import path

from . import views

app_name = "usage_ui"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("connection/<str:name>/", views.connection_detail, name="connection_detail"),
]
