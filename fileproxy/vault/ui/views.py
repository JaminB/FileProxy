from django.conf import settings as django_settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render


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
    gdrive_enabled = bool(django_settings.GOOGLE_CLIENT_ID and django_settings.GOOGLE_CLIENT_SECRET)
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
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
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
def vault_new_dropbox_credentials(request):
    dropbox_enabled = bool(django_settings.DROPBOX_APP_KEY and django_settings.DROPBOX_APP_SECRET)
    return render(request, "vault_ui/new_dropbox.html", {"dropbox_enabled": dropbox_enabled})


@login_required
def vault_oauth_dropbox_callback(request):
    pending = request.session.get("dropbox_oauth_pending")
    error = request.GET.get("error")

    if error or not pending:
        return redirect("/vault/new/dropbox/?error=access_denied")

    app_key = django_settings.DROPBOX_APP_KEY
    app_secret = django_settings.DROPBOX_APP_SECRET
    redirect_uri = pending.get("redirect_uri") or request.build_absolute_uri(
        "/vault/oauth/dropbox/callback/"
    )

    try:
        import dropbox as dbx_sdk

        csrf_session = {"csrf_token": pending.get("csrf_token")}
        flow = dbx_sdk.DropboxOAuth2Flow(
            consumer_key=app_key,
            redirect_uri=redirect_uri,
            session=csrf_session,
            csrf_token_session_key="csrf_token",
            consumer_secret=app_secret,
            token_access_type="offline",
        )
        result = flow.finish(request.GET)
        refresh_token = result.refresh_token
    except Exception:
        return redirect("/vault/new/dropbox/?error=token_exchange_failed")
    finally:
        request.session.pop("dropbox_oauth_pending", None)

    from vault.service import create_dropbox_oauth2_credentials

    item = create_dropbox_oauth2_credentials(
        scope=pending["scope"],
        name=pending["name"],
        secrets_obj={
            "app_key": app_key,
            "app_secret": app_secret,
            "refresh_token": refresh_token,
        },
    )
    return redirect(f"/vault/item/{item.id}/")


@login_required
def vault_new_azure_credentials(request):
    return render(request, "vault_ui/new_azure.html")


@login_required
def vault_guide_s3(request):
    return render(request, "vault_ui/guide_s3.html")


@login_required
def vault_guide_azure(request):
    return render(request, "vault_ui/guide_azure.html")


@login_required
def vault_item_page(request, item_id):
    from files.services import user_scope
    from vault.models import VaultItem

    get_object_or_404(VaultItem, pk=item_id, scope=user_scope(request.user))
    return render(request, "vault_ui/item.html", {"item_id": str(item_id)})
