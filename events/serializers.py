from django.contrib.auth.models import User
from rest_framework import serializers
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

    def validate(self, data):
        start = data.get('start', self.instance.start if self.instance else None)
        end = data.get('end', self.instance.end if self.instance else None)
        if start and end and end <= start:
            raise serializers.ValidationError("End must be after start.")
        return data