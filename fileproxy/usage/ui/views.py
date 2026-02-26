from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def overview(request):
    return render(request, "usage_ui/overview.html")


@login_required
def connection_detail(request, name):
    return render(request, "usage_ui/connection_detail.html", {"connection_name": name})
