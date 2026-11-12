import json
import logging

from django.conf import settings
from pywebpush import WebPushException, webpush

log = logging.getLogger(__name__)


def send_to_user(user, message):
    """Push `message` ({title, body, tag, url}) to every device of `user`.
    Returns how many devices accepted it. Devices the push service says are
    gone (the app was removed, or notifications were turned off) are forgotten."""
    if not settings.VAPID_PRIVATE_KEY:
        return 0  # push isn't set up on this server
    sent = 0
    for subscription in list(user.push_subscriptions.all()):
        try:
            webpush(
                subscription_info={
                    'endpoint': subscription.endpoint,
                    'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth},
                },
                data=json.dumps(message),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={'sub': settings.VAPID_SUBJECT},
                ttl=60 * 60,  # a phone that's off for over an hour doesn't get a stale reminder
                timeout=10,
            )
            sent += 1
        except WebPushException as error:
            status = getattr(error.response, 'status_code', None)
            if status in (404, 410):
                subscription.delete()
            else:
                log.warning('Push to %s failed: %s', subscription.endpoint[:60], error)
    return sent
