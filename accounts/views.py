import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.exceptions import Throttled
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .codes import code_matches, hash_code, new_code, send_code_email, seconds_until_resend
from .models import PendingSignup, ResetCode
from .throttles import CodeCheckThrottle, CodeSendThrottle, LoginThrottle, RegisterThrottle

logger = logging.getLogger(__name__)

BAD_CODE = {'code': ['That code is wrong or has expired.']}


class LoginView(ObtainAuthToken):
    """Username + password in, token out. Limited per IP so passwords can't be guessed freely."""
    throttle_classes = [LoginThrottle]


def clean_password(password, user=None):
    try:
        validate_password(password, user=user)
    except DjangoValidationError as error:
        raise serializers.ValidationError(list(error.messages))
    return password


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, max_length=128)

    def validate_username(self, value):
        value = value.strip()
        field = User._meta.get_field('username')
        for validator in field.validators:
            validator(value)
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('That username is taken.')
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value

    def validate(self, data):
        clean_password(data['password'], User(username=data['username'], email=data['email']))
        return data


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class CodeSerializer(EmailSerializer):
    code = serializers.CharField(max_length=10)


class ResetSerializer(CodeSerializer):
    password = serializers.CharField(write_only=True, max_length=128)


def the_only_user(email):
    """The one active user with this email, or None (none, or ambiguous)."""
    users = list(User.objects.filter(email__iexact=email, is_active=True)[:2])
    return users[0] if len(users) == 1 else None


def public_view(*throttles):
    """Open to anyone, no token needed, with the given rate limits."""
    def decorate(func):
        func = throttle_classes(list(throttles))(func)
        func = permission_classes([AllowAny])(func)
        func = authentication_classes([])(func)
        return api_view(['POST'])(func)
    return decorate


@public_view(RegisterThrottle)
def register(request):
    if not settings.ALLOW_REGISTRATION:
        return Response({'detail': 'Sign-up is closed on this server.'}, status=403)
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    pending = PendingSignup.objects.filter(email=data['email']).first()
    if pending:
        wait = seconds_until_resend(pending)
        if wait:
            raise Throttled(wait=wait)
        pending.delete()

    code = new_code()
    pending = PendingSignup.objects.create(
        email=data['email'],
        username=data['username'],
        password_hash=make_password(data['password']),
        code_hash=hash_code(data['email'], code),
    )
    try:
        send_code_email(data['email'], code, 'finish creating your account')
    except Exception:
        logger.exception('Could not send the sign-up email')
        pending.delete()
        return Response({'detail': "We couldn't send the email. Please try again later."}, status=503)
    return Response({'detail': 'We sent a 6-digit code to your email.'}, status=201)


@public_view(CodeCheckThrottle)
def verify(request):
    serializer = CodeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data['email'].strip().lower()
    pending = PendingSignup.objects.filter(email=email).first()
    if not pending or not code_matches(pending, email, serializer.validated_data['code']):
        return Response(BAD_CODE, status=400)
    try:
        with transaction.atomic():
            user = User(username=pending.username, email=pending.email, password=pending.password_hash)
            user.save()
            pending.delete()
    except IntegrityError:
        pending.delete()
        return Response({'username': ['That username was taken in the meantime. Please sign up again.']}, status=400)
    token, _ = Token.objects.get_or_create(user=user)
    return Response({'token': token.key})


@public_view(CodeSendThrottle)
def resend(request):
    serializer = EmailSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data['email'].strip().lower()
    pending = PendingSignup.objects.filter(email=email).first()
    if pending and not seconds_until_resend(pending):
        code = new_code()
        pending.code_hash = hash_code(email, code)
        pending.attempts = 0
        pending.created_at = timezone.now()
        pending.save()
        try:
            send_code_email(email, code, 'finish creating your account')
        except Exception:
            logger.exception('Could not send the sign-up email')
    # The same answer whether or not there is anything to resend.
    return Response({'detail': 'If that email is waiting to be confirmed, we sent a new code.'})


@public_view(CodeSendThrottle)
def forgot(request):
    serializer = EmailSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data['email'].strip().lower()
    user = the_only_user(email)
    if user:
        existing = ResetCode.objects.filter(user=user).first()
        if not existing or not seconds_until_resend(existing):
            ResetCode.objects.filter(user=user).delete()
            code = new_code()
            ResetCode.objects.create(user=user, code_hash=hash_code(user.pk, code))
            try:
                send_code_email(user.email, code, 'choose a new password')
            except Exception:
                logger.exception('Could not send the password reset email')
    # The same answer whether or not the email has an account.
    return Response({'detail': 'If that email has an account, we sent a code to it.'})


@public_view(CodeCheckThrottle)
def reset(request):
    serializer = ResetSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    user = the_only_user(data['email'].strip().lower())
    entry = ResetCode.objects.filter(user=user).first() if user else None
    if not entry or not code_matches(entry, user.pk, data['code']):
        return Response(BAD_CODE, status=400)
    try:
        clean_password(data['password'], user)
    except serializers.ValidationError as error:
        return Response({'password': error.detail}, status=400)
    user.set_password(data['password'])
    user.save(update_fields=['password'])
    entry.delete()
    Token.objects.filter(user=user).delete()  # signs out every other device
    return Response({'detail': 'Your password was changed. You can sign in now.'})
