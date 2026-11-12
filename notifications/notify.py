import logging

from django.utils import timezone

from push.send import send_to_user
from .models import Notification

log = logging.getLogger(__name__)


def notify(user, kind, actor, event):
    """Save a notification for `user` and push it to their devices. A push
    problem never stops the action that caused it."""
    notification = Notification.objects.create(
        user=user, kind=kind, actor=actor, event_title=event.title, event_start=event.start,
        event=event if event.pk else None,  # a deleted event has no id any more
    )
    when = timezone.localtime(event.start).strftime('%a %d %b, %I:%M %p').replace(' 0', ' ')
    try:
        send_to_user(user, {
            'title': 'My Calendar',
            'body': f'{notification.message} ({when})',
            'tag': f'notification-{notification.id}',
            'url': '/',
        })
    except Exception:  # noqa: BLE001 (network trouble, a push service down...)
        log.exception('Could not push notification %s', notification.id)
    return notification
