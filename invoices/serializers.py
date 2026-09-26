from django.db.models import Sum
from rest_framework import serializers

from invoices.models import Invoice, InvoiceLine, Payment


class InvoiceLineSerializer(serializers.ModelSerializer):
    amount = serializers.FloatField(read_only=True)

    class Meta:
        model = InvoiceLine
        fields = ["id", "description", "quantity", "unit_price", "amount", "position"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "amount", "method", "reference", "received_on", "created_at"]
        read_only_fields = ["created_at", "id"]


class InvoiceSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)
    lines = InvoiceLineSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    balance_due = serializers.FloatField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    days_overdue = serializers.IntegerField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "number",
            "client",
            "client_name",
            "project",
            "project_name",
            "status",
            "issued_on",
            "due_on",
            "currency",
            "tax_rate",
            "discount",
            "subtotal",
            "tax_amount",
            "total",
            "amount_paid",
            "balance_due",
            "is_overdue",
            "days_overdue",
            "notes",
            "lines",
            "payments",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "number",
            "subtotal",
            "tax_amount",
            "total",
            "amount_paid",
            "created_at",
        ]

    def validate(self, attrs):
        request = self.context.get("request")
        client = attrs.get("client") or getattr(self.instance, "client", None)
        if request and client and client.owner_id != request.user.id:
            raise serializers.ValidationError({"client": "Unknown client."})

        project = attrs.get("project") or getattr(self.instance, "project", None)
        if project and client and project.client_id != client.id:
            raise serializers.ValidationError(
                {"project": "That project does not belong to the selected client."}
            )

        issued = attrs.get("issued_on", getattr(self.instance, "issued_on", None))
        due = attrs.get("due_on", getattr(self.instance, "due_on", None))
        if issued and due and due < issued:
            raise serializers.ValidationError({"due_on": "Due date cannot precede the issue date."})

        # A settled invoice is immutable. Reopening one would let a client
        # re-bill work that was already marked paid, so this is refused rather
        # than silently permitted.
        instance = self.instance
        if instance is not None and instance.is_settled:
            requested = attrs.get("status", instance.status)
            if requested != instance.status:
                raise serializers.ValidationError(
                    {"status": "A settled invoice cannot be reopened. Duplicate it instead."}
                )
        return attrs


class GenerateInvoiceSerializer(serializers.Serializer):
    """Turn unbilled time into a draft invoice."""

    client = serializers.IntegerField()
    project = serializers.IntegerField(required=False, allow_null=True)
    due_in_days = serializers.IntegerField(default=14, min_value=1, max_value=365)
    tax_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True
    )
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_client(self, value):
        request = self.context["request"]
        from accounts.models import Client

        if not Client.objects.filter(pk=value, owner=request.user).exists():
            raise serializers.ValidationError("Unknown client.")
        return value

    def validate_project(self, value):
        if value is None:
            return value
        from projects.models import Project

        request = self.context["request"]
        if not Project.objects.filter(pk=value, owner=request.user).exists():
            raise serializers.ValidationError("Unknown project.")
        return value


class RecordPaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    method = serializers.CharField(default="bank_transfer")
    reference = serializers.CharField(required=False, allow_blank=True)
