from django.contrib.auth.models import User
from rest_framework import serializers
from friends.models import friends_of
from .feeds import FeedError, check_url
from .models import Event, Feed, Share


class ShareSerializer(serializers.ModelSerializer):
    """One person an event is shared with, and their answer."""
    username = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = Share
        fields = ['username', 'status']


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            'id', 'title', 'description', 'location', 'start', 'end', 'owner', 'owner_username', 'reminder', 'color',
            'shared_with', 'shares', 'my_status', 'imported_from',
        ]
        read_only_fields = ['id', 'owner']
    
    # People are shared with by username, so clients never need a user list.
    # Adding someone sends them an invite; `shares` shows who has answered.
    shared_with = serializers.SlugRelatedField(
        many=True, slug_field='username', queryset=User.objects.all(), required=False,
    )
    shares = ShareSerializer(many=True, read_only=True)
    # For an event someone shared with you: your answer ("waiting" or "accepted").
    # None on your own events.
    my_status = serializers.SerializerMethodField()
    owner_username = serializers.ReadOnlyField(source='owner.username')
    # {"id", "name"} of the calendar link an event was imported from, else
    # None. Imported events are read-only (CO/BE18).
    imported_from = serializers.SerializerMethodField()

    reminder = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=10080)

    # Only friends can be shared with. Everyone already on the list stays
    # allowed, so editing an old event never fails because of it.
    def validate_shared_with(self, users):
        me = self.context['request'].user
        already = set(self.instance.shared_with.all()) if self.instance else set()
        friends = set(friends_of(me))
        strangers = [u.username for u in users if u not in friends and u not in already]
        if strangers:
            raise serializers.ValidationError(f"You can only share with friends: {', '.join(strangers)}.")
        return users

    def get_my_status(self, event) -> str | None:
        me = self.context['request'].user
        if event.owner_id == me.id:
            return None
        return next((share.status for share in event.shares.all() if share.user_id == me.id), None)

    def get_imported_from(self, event) -> dict | None:
        if event.feed_id is None:
            return None
        return {'id': event.feed_id, 'name': event.feed.name}

    def validate(self, data):
        start = data.get('start', self.instance.start if self.instance else None)
        end = data.get('end', self.instance.end if self.instance else None)
        if start and end and end <= start:
            raise serializers.ValidationError("End must be after start.")
        return data


class InviteAgainSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)


MAX_FEEDS = 10


class FeedSerializer(serializers.ModelSerializer):
    """A calendar link (CO/BE18). The link itself can't be changed after
    adding it: delete it and add the new one."""

    # webcal:// isn't a "URL" to Django, so check_url does the checking.
    url = serializers.CharField(max_length=500)
    event_count = serializers.SerializerMethodField()

    class Meta:
        model = Feed
        fields = ['id', 'name', 'url', 'color', 'last_fetched', 'last_error', 'event_count']
        read_only_fields = ['id', 'last_fetched', 'last_error']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is not None:
            self.fields['url'].read_only = True

    def get_event_count(self, feed) -> int:
        count = getattr(feed, 'event_count', None)
        return feed.events.count() if count is None else count

    def validate_url(self, url):
        try:
            url = check_url(url)
        except FeedError as error:
            raise serializers.ValidationError(str(error))
        if Feed.objects.filter(owner=self.context['request'].user, url=url).exists():
            raise serializers.ValidationError('You already added this link.')
        return url

    def validate(self, data):
        if self.instance is None and Feed.objects.filter(owner=self.context['request'].user).count() >= MAX_FEEDS:
            raise serializers.ValidationError(f'You can add up to {MAX_FEEDS} calendar links.')
        return data
