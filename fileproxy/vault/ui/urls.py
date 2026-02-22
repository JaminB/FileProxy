from django.urls import path

from . import views

app_name = "vault_ui"

urlpatterns = [
    path("", views.vault_page, name="page"),
    path("new/", views.vault_new_credentials, name="new_credentials"),
    path("new/s3/", views.vault_new_s3_credentials, name="new_s3"),
    path("new/gdrive/", views.vault_new_gdrive_credentials, name="new_gdrive"),
    path("oauth/gdrive/callback/", views.vault_oauth_gdrive_callback, name="oauth_gdrive_callback"),
    path("new/dropbox/", views.vault_new_dropbox_credentials, name="new_dropbox"),
    path("oauth/dropbox/callback/", views.vault_oauth_dropbox_callback, name="oauth_dropbox_callback"),
    path("item/<uuid:item_id>/", views.vault_item_page, name="vault_item_page"),
]
