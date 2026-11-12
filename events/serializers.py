from django.contrib.auth.models import User
from rest_framework import serializers
from friends.models import friends_of
from .models import Event

class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ['id', 'title', 'description', 'location', 'start', 'end', 'owner', 'owner_username', 'reminder', 'color', 'shared_with']
        read_only_fields = ['id', 'owner']
    
    # People are shared with by username, so clients never need a user list.
    shared_with = serializers.SlugRelatedField(
        many=True, slug_field='username', queryset=User.objects.all(), required=False,
    )
    owner_username = serializers.ReadOnlyField(source='owner.username')

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

    def validate(self, data):
        start = data.get('start', self.instance.start if self.instance else None)
        end = data.get('end', self.instance.end if self.instance else None)
        if start and end and end <= start:
            raise serializers.ValidationError("End must be after start.")
        return data