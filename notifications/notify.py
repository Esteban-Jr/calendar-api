import logging

from django.utils import timezone

from push.send import send_to_user
from .models import Notification

log = logging.getLogger(__name__)


def push(notification, body):
    """Send a saved notification to the person's devices. A push problem
    never stops the action that caused it."""
    try:
        send_to_user(notification.user, {
            'title': 'My Calendar',
            'body': body,
            'tag': f'notification-{notification.id}',
            'url': '/',
        })
    except Exception:  # noqa: BLE001 (network trouble, a push service down...)
        log.exception('Could not push notification %s', notification.id)


def notify(user, kind, actor, event):
    """Save a notification about an event for `user` and push it."""
    notification = Notification.objects.create(
        user=user, kind=kind, actor=actor, event_title=event.title, event_start=event.start,
        event=event if event.pk else None,  # a deleted event has no id any more
    )
    when = timezone.localtime(event.start).strftime('%a %d %b, %I:%M %p').replace(' 0', ' ')
    push(notification, f'{notification.message} ({when})')
    return notification


def notify_username_change(user, actor, old, new):
    """Tell `user` that `actor` changed their username from `old` to `new`."""
    notification = Notification.objects.create(
        user=user, kind=Notification.USERNAME_CHANGED, actor=actor, old_name=old, new_name=new,
    )
    push(notification, notification.message)
    return notification
