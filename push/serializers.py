from urllib.parse import urlparse

from rest_framework import serializers

# The server sends messages to whatever address a device registers, so only
# accept the real push services. Otherwise someone could make the server send
# requests to addresses of their choosing.
PUSH_SERVICE_HOSTS = (
    'push.apple.com',             # Safari / iPhone (web.push.apple.com)
    'fcm.googleapis.com',         # Chrome, Edge, Android
    'push.services.mozilla.com',  # Firefox
    'notify.windows.com',         # Edge on Windows
)


def is_push_service(url):
    parts = urlparse(url)
    host = (parts.hostname or '').lower()
    return parts.scheme == 'https' and any(host == h or host.endswith('.' + h) for h in PUSH_SERVICE_HOSTS)


class KeysSerializer(serializers.Serializer):
    p256dh = serializers.CharField(max_length=200)
    auth = serializers.CharField(max_length=100)


class SubscriptionSerializer(serializers.Serializer):
    """The browser's PushSubscription as JSON: {endpoint, keys: {p256dh, auth}}."""

    endpoint = serializers.URLField(max_length=1000)
    keys = KeysSerializer()

    def validate_endpoint(self, url):
        if not is_push_service(url):
            raise serializers.ValidationError('That is not a known push service address.')
        return url


class EndpointSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=1000)


class KeySerializer(serializers.Serializer):
    key = serializers.CharField(help_text='The public key browsers need to subscribe')
