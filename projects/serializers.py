from rest_framework import serializers

from projects.models import Project


class ProjectSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    effective_rate = serializers.FloatField(read_only=True)
    hours_logged = serializers.FloatField(read_only=True)
    earned = serializers.FloatField(read_only=True)
    budget_remaining = serializers.FloatField(read_only=True)
    is_over_budget = serializers.BooleanField(read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "client",
            "client_name",
            "name",
            "description",
            "status",
            "hourly_rate",
            "effective_rate",
            "budget",
            "budget_remaining",
            "is_over_budget",
            "hours_logged",
            "earned",
            "started_on",
            "due_on",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate(self, attrs):
        request = self.context.get("request")
        client = attrs.get("client") or getattr(self.instance, "client", None)
        if request and client and client.owner_id != request.user.id:
            raise serializers.ValidationError({"client": "Unknown client."})

        started = attrs.get("started_on", getattr(self.instance, "started_on", None))
        due = attrs.get("due_on", getattr(self.instance, "due_on", None))
        if started and due and due < started:
            raise serializers.ValidationError({"due_on": "Due date cannot precede the start date."})
        return attrs
