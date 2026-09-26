from django.db.models import Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Client, TimeEntry
from accounts.permissions import IsOwner
from accounts.serializers import (
    ChangePasswordSerializer,
    RegisterSerializer,
    TimeEntrySerializer,
    UserSerializer,
)
from clients.serializers import ClientSerializer
from invoices.models import Invoice
from invoices.serializers import InvoiceSerializer


class RegisterView(APIView):
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DashboardView(APIView):
    """Single call that powers the overview screen.

    Doing this in one request keeps the dashboard to a single round trip instead
    of six, and computes the money figures server-side so the client never has
    to reimplement the invoice maths.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        invoices = Invoice.objects.filter(owner=user)

        outstanding = invoices.filter(
            status__in=[Invoice.Status.SENT, Invoice.Status.OVERDUE]
        ).aggregate(t=Sum("total"))["t"] or 0
        collected = invoices.filter(status=Invoice.Status.PAID).aggregate(
            t=Sum("amount_paid")
        )["t"] or 0
        overdue = invoices.filter(
            status=Invoice.Status.SENT, due_on__lt=timezone.localdate()
        ).aggregate(t=Sum("total"))["t"] or 0

        hours = TimeEntry.objects.filter(owner=user).aggregate(t=Sum("hours"))["t"] or 0

        recent = invoices.select_related("client")[:5]

        return Response(
            {
                "clients": {
                    "total": Client.objects.filter(owner=user).count(),
                    "active": Client.objects.filter(owner=user, is_active=True).count(),
                },
                "invoices": {
                    "draft": invoices.filter(status=Invoice.Status.DRAFT).count(),
                    "open": invoices.filter(status__in=Invoice.OPEN_STATUSES).count(),
                    "outstanding_total": round(float(outstanding), 2),
                    "collected_total": round(float(collected), 2),
                    "overdue_total": round(float(overdue), 2),
                },
                "time": {"logged_hours": round(float(hours), 2)},
                "recent_invoices": InvoiceSerializer(recent, many=True).data,
                "top_clients": ClientSerializer(
                    Client.objects.filter(owner=user)[:5], many=True
                ).data,
            }
        )


class TimeEntryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        qs = TimeEntry.objects.filter(owner=self.request.user).select_related("client", "project")
        unbilled = self.request.query_params.get("unbilled")
        if unbilled is not None:
            qs = qs.filter(is_billed=str(unbilled).lower() in {"1", "true", "yes"})
        client = self.request.query_params.get("client")
        if client:
            qs = qs.filter(client_id=client)
        return qs

    def get_serializer_class(self):
        return TimeEntrySerializer

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
