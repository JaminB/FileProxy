from django.conf import settings


def subscription_settings(request):
    return {"SUBSCRIPTIONS_ENABLED": settings.SUBSCRIPTIONS_ENABLED}
