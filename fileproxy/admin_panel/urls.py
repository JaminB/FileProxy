from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="admin-dashboard"),
    path("users/", views.users, name="admin-users"),
    path("users/<int:user_id>/", views.user_detail, name="admin-user-detail"),
    path("beta/", views.beta, name="admin-beta"),
]
