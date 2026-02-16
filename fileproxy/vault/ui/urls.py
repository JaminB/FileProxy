from django.urls import path

from . import views

app_name = "vault_ui"

urlpatterns = [
    path("", views.vault_page, name="page"),
    path("new/", views.vault_new_credentials, name="new_credentials"),
    path("new/s3/", views.vault_new_s3_credentials, name="new_s3"),
    path("item/<int:item_id>/", views.vault_item_page, name="vault_item_page"),
]
