from django.urls import path
from . import views

app_name = "vault_ui"

urlpatterns = [
    path("", views.vault_page, name="page"),
    # New credentials chooser
    path("new/", views.vault_new_credentials, name="new_credentials"),

]