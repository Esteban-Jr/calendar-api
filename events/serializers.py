from rest_framework import serializers
from .models import Event

class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ['id', 'title', 'description', 'location', 'start', 'end', 'owner', 'reminder', 'shared_with']
        read_only_fields = ['id', 'owner']
    
    reminder = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=10080)

    def validate(self, data):
        start = data.get('start', self.instance.start if self.instance else None)
        end = data.get('end', self.instance.end if self.instance else None)
        if start and end and end <= start:
            raise serializers.ValidationError("End must be after start.")
        return data