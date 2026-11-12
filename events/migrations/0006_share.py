"""Sharing gets invites: each person an event is shared with now has a Share
saying whether they've accepted, declined or not answered yet.

Django can't turn a plain many-to-many into one with its own model in place,
so this creates the new Share table, copies every existing share into it as
ACCEPTED (so nothing disappears from anyone's calendar), then swaps the field
over to use it."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def copy_shares_as_accepted(apps, schema_editor):
    Event = apps.get_model('events', 'Event')
    Share = apps.get_model('events', 'Share')
    OldShare = Event.shared_with.through  # the plain table, still there at this point
    Share.objects.bulk_create(
        Share(event_id=old.event_id, user_id=old.user_id, status='accepted')
        for old in OldShare.objects.all()
    )


def copy_shares_back(apps, schema_editor):
    """Going back: everyone except people who declined stays shared."""
    Event = apps.get_model('events', 'Event')
    Share = apps.get_model('events', 'Share')
    OldShare = Event.shared_with.through
    OldShare.objects.bulk_create(
        OldShare(event_id=share.event_id, user_id=share.user_id)
        for share in Share.objects.exclude(status='declined')
    )


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0005_event_reminder_sent_for'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Share',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(
                    choices=[('waiting', 'Waiting for an answer'), ('accepted', 'Accepted'), ('declined', 'Declined')],
                    default='waiting', max_length=10,
                )),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('answered', models.DateTimeField(blank=True, null=True)),
                ('event', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='shares', to='events.event',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='shares', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('event', 'user'), name='one_share_per_person')],
            },
        ),
        migrations.RunPython(copy_shares_as_accepted, copy_shares_back),
        migrations.RemoveField(model_name='event', name='shared_with'),
        migrations.AddField(
            model_name='event',
            name='shared_with',
            field=models.ManyToManyField(
                blank=True, related_name='shared_events', through='events.Share', to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
