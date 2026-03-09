from django.conf import settings
from django.contrib.auth import login
from django.http import Http404
from django.shortcuts import redirect, render

from .forms import UserRegistrationForm


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
