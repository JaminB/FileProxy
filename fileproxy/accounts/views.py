from django.conf import settings
from django.contrib.auth import login
from django.http import Http404
from django.shortcuts import redirect, render

from .forms import UserRegistrationForm
from .models import UserProfile


def register(request):
    if not settings.REGISTRATION_ENABLED:
        raise Http404
    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("/")
    else:
        form = UserRegistrationForm()
    return render(request, "registration/register.html", {"form": form})


def beta_signup(request):
    if not settings.BETA_ENABLED:
        raise Http404
    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            form.save_m2m()
            UserProfile.objects.create(
                user=user,
                status=UserProfile.STATUS_PENDING,
                signup_source=UserProfile.SOURCE_BETA,
            )
            return redirect("beta-pending")
    else:
        form = UserRegistrationForm()
    return render(request, "accounts/beta_signup.html", {"form": form})


def beta_pending(request):
    return render(request, "accounts/beta_pending.html")
