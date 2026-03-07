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
        # The check below is best-effort under concurrency: concurrent requests that
        # all arrive after the interval has elapsed will each read the same stale
        # last_used_at value, pass this check, and each issue an UPDATE. That is
        # benign (a few near-identical writes) and intentionally not prevented here
        # to avoid the overhead of a SELECT FOR UPDATE or advisory lock.
        #
        # Edge case: if last_used_at is ever set to a future timestamp (e.g. after
        # a server clock correction), now - last_used_at will be negative and the
        # UPDATE will be skipped until wall-clock time catches up. The extra guard
        # `now >= api_key.last_used_at` ensures we still update in that scenario.
        if api_key.last_used_at is None or (
            now >= api_key.last_used_at
            and (now - api_key.last_used_at) >= _LAST_USED_UPDATE_INTERVAL
        ):
            APIKey.objects.filter(pk=api_key_id).update(last_used_at=now)
        return (api_key.user, untyped)
