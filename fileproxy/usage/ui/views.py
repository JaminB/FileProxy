from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def overview(request):
    return render(request, "usage_ui/overview.html")


@login_required
def vault_metrics(request):
    return render(request, "usage_ui/vault_metrics.html")
