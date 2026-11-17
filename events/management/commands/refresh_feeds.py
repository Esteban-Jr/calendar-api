from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from events import feeds
from events.models import Feed

STALE_AFTER = timedelta(hours=6)


class Command(BaseCommand):
    help = 'Read calendar links again that were last read over 6 hours ago. The server timer runs this (PL/BE28).'

    def add_arguments(self, parser):
        parser.add_argument('--all', action='store_true', help='Refresh every link, however recent.')

    def handle(self, *args, **options):
        stale = Feed.objects.all()
        if not options['all']:
            cutoff = timezone.now() - STALE_AFTER
            stale = stale.filter(Q(last_fetched__isnull=True) | Q(last_fetched__lt=cutoff))
        refreshed = failed = 0
        for feed in stale.select_related('owner'):
            # One broken link mustn't stop the others; its error is saved on it.
            try:
                feeds.refresh(feed)
                refreshed += 1
            except feeds.FeedError as error:
                failed += 1
                self.stderr.write(f'{feed} (#{feed.pk}): {error}')
        self.stdout.write(f'{refreshed} refreshed, {failed} failed.')
