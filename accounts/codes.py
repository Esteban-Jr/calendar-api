"""One-time email codes: make them, check them, send them."""
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

CODE_LIFETIME = timedelta(minutes=15)
RESEND_AFTER = timedelta(seconds=60)
MAX_ATTEMPTS = 5


def new_code():
    return f'{secrets.randbelow(10**6):06d}'


def hash_code(subject, code):
    """Only a keyed hash of the code is stored. `subject` ties it to one email or user."""
    return salted_hmac('accounts.codes', f'{subject}:{code}').hexdigest()


def seconds_until_resend(entry):
    """0 if a new code may be sent, otherwise how many seconds to wait."""
    wait = entry.created_at + RESEND_AFTER - timezone.now()
    return max(0, int(wait.total_seconds()) + 1) if wait.total_seconds() > 0 else 0


def code_matches(entry, subject, code):
    """True if `code` is right. Wrong guesses are counted, and too many kill the code."""
    expired = timezone.now() - entry.created_at > CODE_LIFETIME
    if expired or entry.attempts >= MAX_ATTEMPTS:
        entry.delete()
        return False
    if constant_time_compare(entry.code_hash, hash_code(subject, str(code).strip())):
        return True
    entry.attempts += 1
    entry.save(update_fields=['attempts'])
    return False


def send_code_email(email, code, reason):
    send_mail(
        subject=f'{code} is your My Calendar code',
        message=(
            f'Your My Calendar code is {code}.\n\n'
            f'Use it to {reason}. It works for 15 minutes.\n\n'
            "If you didn't ask for this, you can ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
