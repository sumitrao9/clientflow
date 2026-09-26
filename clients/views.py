from django.db.models import Count, Q, Sum
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import Client, TimeEntry
from accounts.permissions import IsOwner
from accounts.serializers import TimeEntrySerializer
from clients.serializers import ClientSerializer
from invoices.models import Invoice
from projects.models import Project


class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    filterset_fields = ["status", "is_active"]

    def get_queryset(self):
        qs = (
            Client.objects.filter(owner=self.request.user)
            .annotate(project_count=Count("projects", distinct=True))
            .select_related("owner")
        )
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(company__icontains=search)
                | Q(email__icontains=search)
            )
        return qs

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        """Everything a client page needs, in one request."""
        client = self.get_object()
        invoices = Invoice.objects.filter(client=client)
        time_entries = TimeEntry.objects.filter(client=client)

        return Response(
            {
                "client": ClientSerializer(client).data,
                "totals": {
                    "billed": round(
                        float(invoices.aggregate(t=Sum("total"))["t"] or 0), 2
                    ),
                    "paid": round(
                        float(invoices.aggregate(t=Sum("amount_paid"))["t"] or 0), 2
                    ),
                    "hours_logged": round(
                        float(time_entries.aggregate(t=Sum("hours"))["t"] or 0), 2
                    ),
                },
                "projects": Project.objects.filter(client=client),
                "recent_time": TimeEntrySerializer(
                    time_entries.select_related("project")[:10], many=True
                ).data,
            }
        )

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        client = self.get_object()
        client.is_active = False
        client.status = Client.Status.ARCHIVED
        client.save(update_fields=["is_active", "status", "updated_at"])
        return Response(ClientSerializer(client).data)
