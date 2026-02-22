from django.conf import settings as django_settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


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
def vault_new_gdrive_credentials(request):
    gdrive_enabled = bool(
        django_settings.GOOGLE_CLIENT_ID and django_settings.GOOGLE_CLIENT_SECRET
    )
    return render(request, "vault_ui/new_gdrive.html", {"gdrive_enabled": gdrive_enabled})


@login_required
def vault_oauth_gdrive_callback(request):
    pending = request.session.get("gdrive_oauth_pending")
    error = request.GET.get("error")

    if error or not pending:
        return redirect("/vault/new/gdrive/?error=access_denied")

    if request.GET.get("state") != pending.get("state"):
        return redirect("/vault/new/gdrive/?error=state_mismatch")

    code = request.GET.get("code")
    if not code:
        return redirect("/vault/new/gdrive/?error=missing_code")

    client_id = django_settings.GOOGLE_CLIENT_ID
    client_secret = django_settings.GOOGLE_CLIENT_SECRET

    try:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(
            {"web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }},
            scopes=["https://www.googleapis.com/auth/drive"],
            state=pending["state"],
        )
        flow.redirect_uri = request.build_absolute_uri("/vault/oauth/gdrive/callback/")
        flow.fetch_token(code=code)
        refresh_token = flow.credentials.refresh_token
    except Exception:
        return redirect("/vault/new/gdrive/?error=token_exchange_failed")
    finally:
        request.session.pop("gdrive_oauth_pending", None)

    from vault.service import create_gdrive_oauth2_credentials
    item = create_gdrive_oauth2_credentials(
        scope=pending["scope"],
        name=pending["name"],
        secrets_obj={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
    )
    return redirect(f"/vault/item/{item.id}/")


@login_required
def vault_item_page(request, item_id: int):
    return render(request, "vault_ui/item.html", {"item_id": item_id})
