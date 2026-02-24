from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def overview(request):
    return render(request, "usage_ui/overview.html")


@login_required
def vault_detail(request, name):
    return render(request, "usage_ui/vault_detail.html", {"vault_name": name})
