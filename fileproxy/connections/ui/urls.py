from django.urls import path

from . import views

app_name = "connections_ui"

urlpatterns = [
    path("", views.connections_page, name="page"),
    path("new/", views.connections_new_credentials, name="new_credentials"),
    path("new/s3/", views.connections_new_s3_credentials, name="new_s3"),
    path("new/gdrive/", views.connections_new_gdrive_credentials, name="new_gdrive"),
    path(
        "oauth/gdrive/callback/",
        views.connections_oauth_gdrive_callback,
        name="oauth_gdrive_callback",
    ),
    path("new/dropbox/", views.connections_new_dropbox_credentials, name="new_dropbox"),
    path(
        "oauth/dropbox/callback/",
        views.connections_oauth_dropbox_callback,
        name="oauth_dropbox_callback",
    ),
    path("new/azure/", views.connections_new_azure_credentials, name="new_azure"),
    path("new/s3/guide/", views.connections_guide_s3, name="guide_s3"),
    path("new/azure/guide/", views.connections_guide_azure, name="guide_azure"),
    path("item/<uuid:item_id>/", views.connection_item_page, name="connection_item_page"),
]
