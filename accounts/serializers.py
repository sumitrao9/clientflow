from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from accounts.models import TimeEntry

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "business_name",
            "hourly_rate",
            "default_currency",
            "invoice_prefix",
        ]
        read_only_fields = ["id", "invoice_prefix"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})
    password_confirm = serializers.CharField(write_only=True, style={"input_type": "password"})
    email = serializers.EmailField()

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
            "business_name",
            "hourly_rate",
        ]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        try:
            validate_password(attrs["password"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        if value == self.initial_data.get("current_password"):
            raise serializers.ValidationError("New password must differ from the current one.")
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class TimeEntrySerializer(serializers.ModelSerializer):
    amount = serializers.FloatField(read_only=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)
    hourly_rate = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        help_text="Optional. Defaults to the project rate, else the client rate.",
    )

    class Meta:
        model = TimeEntry
        fields = [
            "id",
            "client",
            "client_name",
            "project",
            "project_name",
            "description",
            "hours",
            "hourly_rate",
            "amount",
            "logged_on",
            "is_billed",
            "created_at",
        ]
        read_only_fields = ["created_at", "is_billed"]

    def validate(self, attrs):
        request = self.context.get("request")
        if request:
            client = attrs.get("client") or getattr(self.instance, "client", None)
            if client and client.owner_id != request.user.id:
                raise serializers.ValidationError({"client": "Unknown client."})

            project = attrs.get("project") or getattr(self.instance, "project", None)
            if project and client and project.client_id != client.id:
                raise serializers.ValidationError(
                    {"project": "That project does not belong to the selected client."}
                )

        hours = attrs.get("hours", getattr(self.instance, "hours", None))
        if hours is not None and hours <= 0:
            raise serializers.ValidationError({"hours": "Hours must be greater than zero."})
        return attrs
