from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from accounts.forms import NotificationPreferencesForm, ProfileUpdateForm
from accounts.models import NotificationPreferences
from subscription.models import SubscriptionPlan


def _require_staff(request):
    if not request.user.is_authenticated:
        from django.conf import settings
        from django.shortcuts import redirect as _redirect

        return _redirect(f"{settings.LOGIN_URL}?next={request.path}")
    if not request.user.is_staff:
        raise Http404
    return None


@login_required
def profile(request):
    prefs, _ = NotificationPreferences.objects.get_or_create(user=request.user)

    if request.method == "POST":
        profile_form = ProfileUpdateForm(request.POST, instance=request.user)
        prefs_form = NotificationPreferencesForm(request.POST, instance=prefs)
        if profile_form.is_valid() and prefs_form.is_valid():
            profile_form.save()
            prefs_form.save()
            messages.success(request, "Profile updated.")
            return redirect("profile")
    else:
        profile_form = ProfileUpdateForm(instance=request.user)
        prefs_form = NotificationPreferencesForm(instance=prefs)

    return render(
        request,
        "accounts/profile.html",
        {
            "profile_form": profile_form,
            "prefs_form": prefs_form,
        },
    )


def user_list(request):
    denied = _require_staff(request)
    if denied:
        return denied
    plans = SubscriptionPlan.objects.filter(expires_at__isnull=True).order_by("name")
    return render(request, "accounts/users/user_list.html", {"plans": plans})


def user_detail(request, user_id):
    denied = _require_staff(request)
    if denied:
        return denied
    target_user = get_object_or_404(
        User.objects.select_related("profile", "subscription__plan"), pk=user_id
    )
    plans = SubscriptionPlan.objects.filter(expires_at__isnull=True).order_by("name")
    return render(
        request,
        "accounts/users/user_detail.html",
        {
            "target_user": target_user,
            "plans": plans,
        },
    )
