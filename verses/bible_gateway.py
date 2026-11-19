"""Bible Gateway's free NTV verse of the day (CO/BE19). Only their public
daily verse is used, always with their link and copyright link."""
import html

import requests

URL = 'https://www.biblegateway.com/votd/get/?format=json&version=NTV'
TIMEOUT = 5  # seconds


class VerseUnavailable(Exception):
    """Bible Gateway is down, slow, or sent something we can't use."""


def _clean(value, limit=None):
    text = html.unescape(str(value or '')).strip()
    return text[:limit] if limit else text


def fetch_votd():
    """Today's verse from Bible Gateway, as DailyVerse fields."""
    try:
        response = requests.get(URL, timeout=TIMEOUT)
    except requests.RequestException:
        raise VerseUnavailable()
    if response.status_code != 200:
        raise VerseUnavailable()
    try:
        votd = response.json()['votd']
        fields = {
            'text': _clean(votd.get('rawtext')),
            'reference': _clean(votd.get('display_ref'), 100),
            'version_name': _clean(votd.get('version'), 100),
            'link': _clean(votd.get('permalink'), 500),
            'copyright_link': _clean(votd.get('copyrightlink'), 500),
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        raise VerseUnavailable()
    # Without the verse, its reference or Bible Gateway's links we can't show
    # it properly (the credit is required), so treat it as unavailable.
    links_ok = all(fields[name].startswith('https://') for name in ('link', 'copyright_link'))
    if not fields['text'] or not fields['reference'] or not links_ok:
        raise VerseUnavailable()
    return fields
