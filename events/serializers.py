from django.contrib.auth.models import User
from rest_framework import serializers
from friends.models import friends_of
from .models import Event, Share, Tag


class ShareSerializer(serializers.ModelSerializer):
    """One person an event is shared with, and their answer."""
    username = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = Share
        fields = ['username', 'status']


class TagNamesField(serializers.ListField):
    """An event's tags as a list of names: reads the Tag rows, takes names."""
    child = serializers.CharField(max_length=30, trim_whitespace=True)

    def to_representation(self, tags):
        return [tag.name for tag in tags.all()]


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            'id', 'title', 'description', 'location', 'start', 'end', 'owner', 'owner_username', 'reminder', 'color',
            'shared_with', 'shares', 'my_status', 'tags',
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

    reminder = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=10080)

    # The owner's own labels, as names A-Z. Friends an event is shared with
    # see an empty list (tags are private). Sending `tags` replaces them all;
    # leaving it out of a PATCH keeps them.
    tags = TagNamesField(required=False, max_length=20)

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

    def validate_tags(self, names):
        # No commas: ?tags=work,football splits on them, so "rock,pop" could
        # never be found (CO/BE16).
        if any(',' in name for name in names):
            raise serializers.ValidationError("Tag names can't contain commas.")
        # Tidy: lowercase, and the same tag only once ("Work" and "work" are one).
        return sorted({name.lower() for name in names})

    def to_representation(self, event):
        data = super().to_representation(event)
        me = self.context['request'].user
        if event.owner_id != me.id:
            data['tags'] = []
        return data

    def _save_tags(self, event, names):
        if names is not None:
            event.tags.set([Tag.objects.get_or_create(owner=event.owner, name=name)[0] for name in names])

    def create(self, validated_data):
        names = validated_data.pop('tags', None)
        event = super().create(validated_data)
        self._save_tags(event, names)
        return event

    def update(self, event, validated_data):
        names = validated_data.pop('tags', None)
        event = super().update(event, validated_data)
        self._save_tags(event, names)
        return event

    def get_my_status(self, event) -> str | None:
        me = self.context['request'].user
        if event.owner_id == me.id:
            return None
        return next((share.status for share in event.shares.all() if share.user_id == me.id), None)

    def validate(self, data):
        start = data.get('start', self.instance.start if self.instance else None)
        end = data.get('end', self.instance.end if self.instance else None)
        if start and end and end <= start:
            raise serializers.ValidationError("End must be after start.")
        return data


class InviteAgainSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
