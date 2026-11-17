from rest_framework import serializers

from .models import DailyVerse


class DailyVerseSerializer(serializers.ModelSerializer):
    version = serializers.SerializerMethodField()
    # True when Bible Gateway couldn't be reached today and this is the last
    # verse we had.
    stale = serializers.SerializerMethodField()

    class Meta:
        model = DailyVerse
        fields = ['date', 'text', 'reference', 'version', 'version_name', 'link', 'copyright_link', 'stale']

    def get_version(self, verse) -> str:
        return 'NTV'

    def get_stale(self, verse) -> bool:
        return verse.date != self.context['today']
