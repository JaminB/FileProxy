from django.urls import path

from . import views

app_name = "subscription_ui"

urlpatterns = [
    path("plans/", views.plans_page, name="plans"),
    path("plans/new/", views.new_plan_page, name="new_plan"),
    path("plans/<uuid:plan_id>/", views.plan_detail_page, name="plan_detail"),
    path("my/", views.my_subscription_page, name="my_subscription"),
]
