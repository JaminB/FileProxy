from datetime import timedelta

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import UntypedToken

from .models import APIKey
from .tokens import APIKeyToken

# Only write `last_used_at` to the database at most once per this interval.
# This avoids a SQL UPDATE on every single authenticated request.
_LAST_USED_UPDATE_INTERVAL = timedelta(minutes=1)


class APIKeyAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return 'Bearer realm="api"'

    def authenticate(self, request):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            return None  # pass to SessionAuthentication
        raw = auth[len("Bearer ") :]
        try:
            untyped = UntypedToken(raw)
        except TokenError as e:
            raise AuthenticationFailed(str(e))
        if untyped.get("token_type") != APIKeyToken.token_type:
            return None  # not our token
        api_key_id = untyped.get("api_key_id")
        if not api_key_id:
            raise AuthenticationFailed("Malformed API key token.")
        try:
            api_key = APIKey.objects.select_related("user").get(pk=api_key_id)
        except APIKey.DoesNotExist:
            raise AuthenticationFailed("API key has been revoked or is invalid.")
        now = timezone.now()
        if api_key.last_used_at is None or (now - api_key.last_used_at) >= _LAST_USED_UPDATE_INTERVAL:
            APIKey.objects.filter(pk=api_key_id).update(last_used_at=now)
        return (api_key.user, untyped)
