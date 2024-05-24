import hashlib
import hmac

from allauth.account import app_settings
from allauth.account.adapter import get_adapter
from allauth.account.models import EmailAddress
from allauth.account.utils import filter_users_by_email
from allauth.socialaccount.models import SocialApp
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import User


class SocialAppSerializer(serializers.ModelSerializer):
    authorize_url = serializers.SerializerMethodField()
    scopes = serializers.SerializerMethodField()
    provider = serializers.SerializerMethodField()

    class Meta:
        model = SocialApp
        fields = ("provider", "name", "client_id", "authorize_url", "scopes")

    def get_authorize_url(self, obj):
        request = self.context.get("request")
        adapter_cls = SOCIAL_ADAPTER_MAP.get(obj.provider)
        if adapter_cls == OpenIDConnectAdapter:
            adapter = adapter_cls(request, obj.provider_id)
        else:
            adapter = adapter_cls(request)
        if adapter:
            return adapter.authorize_url

    def get_scopes(self, obj):
        request = self.context.get("request")
        if request:
            provider = obj.get_provider(request)
            return provider.get_scope(request)

    def get_provider(self, obj):
        return obj.provider_id or obj.provider


class ConfirmEmailAddressSerializer(serializers.Serializer):
    email = serializers.EmailField()


class EmailAddressSerializer(serializers.ModelSerializer):
    isPrimary = serializers.BooleanField(source="primary", read_only=True)
    email = serializers.EmailField()  # Remove default unique validation
    isVerified = serializers.BooleanField(source="verified", read_only=True)

    class Meta:
        model = EmailAddress
        fields = ("isPrimary", "email", "isVerified")

    def clean_email(self):
        """Validate email as done in allauth.account.forms.AddEmailForm"""
        value = self.cleaned_data["email"]
        value = get_adapter().clean_email(value)
        errors = {
            "this_account": _(
                "This e-mail address is already associated" " with this account."
            ),
            "different_account": _(
                "This e-mail address is already associated" " with another account."
            ),
        }
        users = filter_users_by_email(value)
        on_this_account = [u for u in users if u.pk == self.user.pk]
        on_diff_account = [u for u in users if u.pk != self.user.pk]

        if on_this_account:
            raise serializers.ValidationError(errors["this_account"])
        if on_diff_account and app_settings.UNIQUE_EMAIL:
            raise serializers.ValidationError(errors["different_account"])
        return value

    def validate(self, attrs):
        if self.context["request"].method == "POST":
            # Run extra validation on create
            self.user = self.context["request"].user
            self.cleaned_data = attrs
            attrs["email"] = self.clean_email()
        return attrs

    def create(self, validated_data):
        return EmailAddress.objects.add_email(
            self.context["request"], self.user, validated_data["email"], confirm=True
        )

    def update(self, instance, validated_data):
        instance.primary = True
        instance.save()
        return instance


class UserSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="email", read_only=True)
    lastLogin = serializers.DateTimeField(source="last_login", read_only=True)
    isSuperuser = serializers.BooleanField(source="is_superuser")
    emails = EmailAddressSerializer(many=True, default=[])
    id = serializers.CharField()
    isActive = serializers.BooleanField(source="is_active")
    dateJoined = serializers.DateTimeField(source="created", read_only=True)
    hasPasswordAuth = serializers.BooleanField(
        source="has_usable_password", read_only=True
    )

    class Meta:
        model = User
        fields = (
            "username",
            "lastLogin",
            "isSuperuser",
            "emails",
            "identities",
            "id",
            "isActive",
            "name",
            "dateJoined",
            "hasPasswordAuth",
            "email",
            "options",
        )


class CurrentUserSerializer(UserSerializer):
    chatwootIdentifierHash = serializers.SerializerMethodField()

    def get_chatwootIdentifierHash(self, obj):
        if settings.CHATWOOT_WEBSITE_TOKEN and settings.CHATWOOT_IDENTITY_TOKEN:
            secret = bytes(settings.CHATWOOT_IDENTITY_TOKEN, "utf-8")
            message = bytes(str(obj.id), "utf-8")

            hash = hmac.new(secret, message, hashlib.sha256)
            return hash.hexdigest()


class UserNotificationsSerializer(serializers.ModelSerializer):
    subscribeByDefault = serializers.BooleanField(source="subscribe_by_default")

    class Meta:
        model = User
        fields = ("subscribeByDefault",)
