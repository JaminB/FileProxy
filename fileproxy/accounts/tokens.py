from datetime import timedelta

from rest_framework_simplejwt.tokens import Token


class APIKeyToken(Token):
    token_type = "api_key"
    lifetime = timedelta(days=3650)  # ~10 years

    @classmethod
    def for_api_key(cls, api_key) -> "APIKeyToken":
        token = cls()
        token["user_id"] = api_key.user_id
        token["api_key_id"] = str(api_key.id)
        return token
