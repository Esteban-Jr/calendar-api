from django.core.management.base import BaseCommand
from django.utils import timezone

from events.models import Event
from push.reminders import GRACE, LONGEST_REMINDER, is_due, message_for
from push.send import send_to_user


class Command(BaseCommand):
    help = 'Push the reminders that are due now. The server runs this every minute.'

    def handle(self, *args, **options):
        now = timezone.now()
        # Only events whose reminder could possibly be due: starting between a
        # few minutes ago and a week from now (the longest reminder).
        candidates = (
            Event.objects.filter(reminder__isnull=False, start__gte=now - GRACE, start__lte=now + LONGEST_REMINDER)
            .select_related('owner')
        )
        count = 0
        for event in candidates:
            if not is_due(event, now):
                continue
            send_to_user(event.owner, message_for(event, now))
            # Remember which start time this was for: if the event is moved, it reminds again.
            Event.objects.filter(pk=event.pk).update(reminder_sent_for=event.start)
            count += 1
        if count:
            self.stdout.write(f'Sent {count} reminder(s).')
