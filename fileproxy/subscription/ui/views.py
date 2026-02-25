from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def plans_page(request):
    return render(request, "subscription_ui/plans.html")


@login_required
def new_plan_page(request):
    if not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Staff only.")
    return render(request, "subscription_ui/new_plan.html")


@login_required
def plan_detail_page(request, plan_id):
    if not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Staff only.")
    return render(request, "subscription_ui/plan_detail.html", {"plan_id": str(plan_id)})


@login_required
def my_subscription_page(request):
    return render(request, "subscription_ui/my_subscription.html")
