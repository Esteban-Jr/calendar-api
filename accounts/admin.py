from django.contrib import admin

from .models import PendingSignup


@admin.register(PendingSignup)
class PendingSignupAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'created_at', 'attempts')
    exclude = ('password_hash', 'code_hash')
