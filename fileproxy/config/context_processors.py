from django.conf import settings


def subscription_settings(_request):
    return {
        "SUBSCRIPTIONS_ENABLED": settings.SUBSCRIPTIONS_ENABLED,
        "REGISTRATION_ENABLED": settings.REGISTRATION_ENABLED,
    }
