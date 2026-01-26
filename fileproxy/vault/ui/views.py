from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def vault_page(request):
    return render(request, "vault_ui/vault.html")

def vault_new_credentials(request):
    return render(request, "vault_ui/new_credentials.html")

@login_required
def vault_new_s3_page(request):
    return render(request, "vault_ui/new_s3.html")
