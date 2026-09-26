from rest_framework import serializers

from accounts.models import Client


class ClientSerializer(serializers.ModelSerializer):
    outstanding_balance = serializers.SerializerMethodField()
    effective_rate = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            "id",
            "name",
            "company",
            "email",
            "phone",
            "status",
            "hourly_rate",
            "effective_rate",
            "outstanding_balance",
            "notes",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_outstanding_balance(self, obj) -> dict:
        money = obj.outstanding_balance
        return {"gross": money.gross, "paid": money.paid, "due": money.balance_due}

    def get_effective_rate(self, obj) -> float:
        return obj.effective_rate

    def validate_email(self, value):
        if not value:
            return value
        from django.core.validators import validate_email

        validate_email(value)
        return value

    def validate_name(self, value):
        # DRF does not derive a field-level validator from a model
        # UniqueConstraint, so the duplicate would otherwise surface as a raw
        # IntegrityError and a 409. Checking it here returns a 400 naming the
        # offending field, which is what a client can actually act on.
        request = self.context.get("request")
        if not request:
            return value
        clash = Client.objects.filter(owner=request.user, name__iexact=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("You already have a client with this name.")
        return value
