from datetime import timedelta

from django.db.models import Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import Client
from accounts.permissions import IsOwner
from config.exceptions import error_response
from invoices.models import Invoice, Payment
from invoices.pdf import render_invoice_pdf
from invoices.serializers import (
    GenerateInvoiceSerializer,
    InvoiceSerializer,
    RecordPaymentSerializer,
)


class InvoiceViewSet(viewsets.ModelViewSet):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    filterset_fields = ["status", "client", "project"]

    def get_queryset(self):
        qs = (
            Invoice.objects.filter(owner=self.request.user)
            .select_related("client", "project")
            .prefetch_related("lines", "payments")
        )
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(number__icontains=search) | Q(client__name__icontains=search)
            )
        overdue = self.request.query_params.get("overdue")
        if overdue is not None and str(overdue).lower() in {"1", "true", "yes"}:
            qs = qs.filter(
                status=Invoice.Status.SENT, due_on__lt=timezone.localdate(), total__gt=0
            )
        return qs

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """Create a draft invoice from unbilled time entries."""
        serializer = GenerateInvoiceSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        invoice = Invoice.objects.create(
            owner=request.user,
            client_id=data["client"],
            project_id=data.get("project"),
            due_on=timezone.localdate() + timedelta(days=data["due_in_days"]),
            tax_rate=data.get("tax_rate") or 0,
            notes=data.get("notes", ""),
        )
        created = invoice.generate_from_time()
        invoice.refresh_from_db()

        return Response(
            {"invoice": InvoiceSerializer(invoice).data, "line_items_created": created},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        """Mark a draft as sent, refusing to send an empty invoice."""
        invoice = self.get_object()
        if not invoice.lines.exists():
            return error_response(
                "Cannot send an invoice with no line items.", code="empty_invoice"
            )
        if invoice.total <= 0:
            return error_response(
                "Cannot send an invoice with a zero total.", code="zero_total"
            )
        invoice.status = Invoice.Status.SENT
        invoice.save(update_fields=["status", "updated_at"])
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"])
    def payments(self, request, pk=None):
        invoice = self.get_object()
        if invoice.is_settled:
            return error_response(
                "This invoice is already settled.", code="invoice_settled"
            )
        serializer = RecordPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = float(serializer.validated_data["amount"])
        if amount <= 0:
            return error_response(
                "Payment must be greater than zero.",
                details={"amount": ["Payment must be greater than zero."]},
            )
        if amount > invoice.balance_due:
            return error_response(
                f"Payment exceeds the balance due ({invoice.balance_due}).",
                details={"amount": [f"Maximum payable is {invoice.balance_due}."]},
            )

        Payment.objects.create(
            invoice=invoice,
            amount=amount,
            method=serializer.validated_data["method"],
            reference=serializer.validated_data.get("reference", ""),
        )
        invoice.refresh_from_db()
        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        invoice = self.get_object()
        invoice.status = Invoice.Status.VOID
        invoice.save(update_fields=["status", "updated_at"])
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        invoice = self.get_object()
        pdf = render_invoice_pdf(invoice)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{invoice.slug}.pdf"'
        return response

    @action(detail=False, methods=["get"])
    def receivables(self, request):
        """Who owes what, grouped by client."""
        rows = (
            Invoice.objects.filter(
                owner=request.user, status__in=[Invoice.Status.SENT, Invoice.Status.OVERDUE]
            )
            .values("client__id", "client__name", "client__email")
            .annotate(outstanding=Sum("total"), paid=Sum("amount_paid"))
            .order_by("-outstanding")
        )

        today = timezone.localdate()
        data = [
            {
                "client_id": r["client__id"],
                "client_name": r["client__name"],
                "client_email": r["client__email"],
                "outstanding": round(float(r["outstanding"] or 0), 2),
                "paid": round(float(r["paid"] or 0), 2),
                "due": round(float(r["outstanding"] or 0) - float(r["paid"] or 0), 2),
            }
            for r in rows
        ]
        return Response({"as_of": today, "rows": data})
