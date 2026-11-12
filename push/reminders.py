"""Which reminders are due, and how to word them. The rules and wording match
the web app's src/reminders.js, so a reminder reads the same whether the app
shows it (while open) or the server pushes it (while closed)."""
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

GRACE = timedelta(minutes=5)  # still worth sending a few minutes after the start
LONGEST_REMINDER = timedelta(minutes=10080)  # the API allows up to a week


def remind_at(event):
    return event.start - timedelta(minutes=event.reminder)


def is_due(event, now):
    return remind_at(event) <= now < event.start + GRACE and event.reminder_sent_for != event.start


def describe_start(start, now):
    minutes = round((start - now).total_seconds() / 60)
    if minutes <= -1:
        return f'Started {-minutes} min ago'
    if minutes < 1:
        return 'Starting now'
    if minutes < 60:
        return f'Starts in {minutes} min'
    if minutes < 24 * 60:
        hours, rest = divmod(minutes, 60)
        return f"Starts in {hours} {'hr' if hours == 1 else 'hrs'}{f' {rest} min' if rest else ''}"
    days = round(minutes / (24 * 60))
    return f"Starts in {days} day{'' if days == 1 else 's'}"


def message_for(event, now):
    start_text = serializers.DateTimeField().to_representation(event.start)  # exactly as the API shows it
    time = timezone.localtime(event.start).strftime('%I:%M %p').lstrip('0')
    detail = ' · '.join(part for part in [time, event.location] if part)
    return {
        'title': event.title,
        'body': f'{describe_start(event.start, now)} · {detail}',
        # Same tag as the app uses, so if the app is open too the phone shows one notification, not two.
        'tag': f'{event.id}|{start_text}|{event.reminder}',
        'url': '/',
    }
