from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def vault_page(request):
    return render(request, "vault_ui/vault.html")

@login_required
def vault_new_credentials(request):
    return render(request, "vault_ui/new_credentials.html")

@login_required
def vault_new_s3_credentials(request):
    return render(request, "vault_ui/new_s3.html")

@login_required
def vault_item_page(request, item_id: int):
    return render(request, "vault_ui/item.html", {"item_id": item_id})

