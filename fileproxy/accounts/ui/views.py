from accounts.forms import NotificationPreferencesForm, ProfileUpdateForm
from accounts.models import NotificationPreferences
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


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
