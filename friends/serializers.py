from rest_framework import serializers


class FriendRequestSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)


# The shapes the API answers with (used for the docs page).
class PersonSerializer(serializers.Serializer):
    id = serializers.IntegerField(help_text='The friendship / request id')
    username = serializers.CharField()


class FriendListSerializer(serializers.Serializer):
    friends = PersonSerializer(many=True)
    incoming = PersonSerializer(many=True, help_text='Requests sent to me')
    outgoing = PersonSerializer(many=True, help_text='Requests I sent')
