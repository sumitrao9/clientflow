import uuid

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import Client, TimeEntry, User
from projects.models import Project


class Invoice(models.Model):
    """A bill sent to a client.

    Totals are recalculated and stored on save so that list endpoints never have
    to walk line items. ``recalculate()`` is the single source of truth for the
    money maths and is also what the PDF renderer uses.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"
        VOID = "void", "Void"

    OPEN_STATUSES = (Status.DRAFT, Status.SENT, Status.OVERDUE)
    SETTLED_STATUSES = (Status.PAID, Status.VOID)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="invoices")
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="invoices")
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices"
    )
    number = models.CharField(max_length=32, editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)

    issued_on = models.DateField(default=timezone.localdate)
    due_on = models.DateField()
    currency = models.CharField(max_length=3, default="USD")

    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Percentage, e.g. 18 for 18% GST.",
    )
    discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )

    # Denormalised totals, recomputed on every save via recalculate().
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issued_on", "-created_at"]
        indexes = [
            models.Index(fields=["owner", "-issued_on"]),
            models.Index(fields=["owner", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["owner", "number"], name="uniq_invoice_number_per_owner")
        ]

    def __str__(self) -> str:
        return f"{self.number} ({self.client})"

    # -- money maths ------------------------------------------------------

    def recalculate(self) -> None:
        """Recompute subtotal, tax and total from the current line items."""
        subtotal = sum((line.amount for line in self.lines.all()), 0)
        subtotal = round(subtotal, 2)
        taxable = max(subtotal - float(self.discount or 0), 0)
        tax = round(taxable * float(self.tax_rate or 0) / 100, 2)

        self.subtotal = subtotal
        self.tax_amount = tax
        self.total = round(taxable + tax, 2)

    @property
    def balance_due(self) -> float:
        return round(float(self.total) - float(self.amount_paid), 2)

    @property
    def is_settled(self) -> bool:
        return self.status in self.SETTLED_STATUSES

    @property
    def is_overdue(self) -> bool:
        return (
            self.status == Invoice.Status.SENT
            and self.balance_due > 0
            and self.due_on < timezone.localdate()
        )

    @property
    def days_overdue(self) -> int:
        if not self.is_overdue:
            return 0
        return (timezone.localdate() - self.due_on).days

    @property
    def slug(self) -> str:
        return slugify(self.number)

    def mark_paid(self, amount: float | None = None) -> None:
        """Record a payment and settle the invoice once fully covered."""
        applied = self.balance_due if amount is None else round(min(amount, self.balance_due), 2)
        self.amount_paid = round(float(self.amount_paid) + applied, 2)
        if self.balance_due <= 0:
            self.status = Invoice.Status.PAID
        self.save(update_fields=["amount_paid", "status", "updated_at"])

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = self.owner.allocate_invoice_number()
        if not self.currency:
            self.currency = self.owner.default_currency
        self.recalculate()
        if self.amount_paid >= float(self.total) and float(self.total) > 0:
            self.status = Invoice.Status.PAID
        super().save(*args, **kwargs)

    # -- generation -------------------------------------------------------

    def generate_from_time(self, entries: list[TimeEntry] | None = None) -> int:
        """Create line items from unbilled time entries.

        Pass ``entries`` to bill a specific set; omit it to bill every unbilled
        entry for this client (optionally narrowed to the invoice's project).
        """
        if entries is None:
            qs = TimeEntry.objects.filter(client=self.client, is_billed=False)
            if self.project_id:
                qs = qs.filter(project=self.project_id)
            entries = list(qs.select_related("project"))

        created = 0
        new_lines = [
            InvoiceLine(
                invoice=self,
                description=entry.description,
                quantity=entry.hours,
                unit_price=entry.hourly_rate,
                time_entry=entry,
                position=idx,
            )
            for idx, entry in enumerate(entries)
        ]
        # bulk_create bypasses InvoiceLine.save(), so the parent total is synced
        # once at the end rather than once per line.
        InvoiceLine.objects.bulk_create(new_lines)
        created = len(new_lines)

        if entries:
            TimeEntry.objects.filter(pk__in=[e.pk for e in entries]).update(is_billed=True)

        self.recalculate()
        self.save()
        return created


class InvoiceLine(models.Model):
    """One billable row. Either ad-hoc, or generated from a TimeEntry."""

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=300)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    time_entry = models.ForeignKey(
        TimeEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_lines",
    )
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self) -> str:
        return f"{self.quantity} x {self.description[:40]}"

    @property
    def amount(self) -> float:
        return round(float(self.quantity) * float(self.unit_price), 2)

    def _sync_invoice(self):
        """Keep the parent invoice's cached totals honest.

        Line items can be added, edited or removed after the invoice itself was
        last saved, so every write has to push the new subtotal/tax/total back up
        to the invoice rather than waiting for the next Invoice.save().
        """
        invoice = self.invoice
        invoice.recalculate()
        invoice.save()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._sync_invoice()

    def delete(self, *args, **kwargs):
        invoice = self.invoice
        super().delete(*args, **kwargs)
        invoice.recalculate()
        invoice.save()


class Payment(models.Model):
    """A payment received against an invoice."""

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=32, default="bank_transfer")
    reference = models.CharField(max_length=80, blank=True)
    received_on = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_on", "-created_at"]

    def __str__(self) -> str:
        return f"{self.amount} on {self.received_on}"

    def save(self, *args, **kwargs):
        # A payment can never exceed the outstanding balance. Clamping here
        # rather than in the API keeps the ledger self-consistent for any caller
        # (admin, shell, management command) and guarantees balance_due is never
        # negative, which would otherwise render as a nonsense negative invoice.
        outstanding = float(self.invoice.balance_due)
        if outstanding <= 0:
            raise ValueError("Invoice has no outstanding balance to pay.")
        if float(self.amount) > outstanding:
            self.amount = outstanding

        super().save(*args, **kwargs)

        # Keep the invoice's cached paid figure in step with its payments.
        total_paid = self.invoice.payments.aggregate(t=models.Sum("amount"))["t"] or 0
        self.invoice.amount_paid = total_paid
        if self.invoice.balance_due <= 0 and self.invoice.status != Invoice.Status.VOID:
            self.invoice.status = Invoice.Status.PAID
        self.invoice.save(update_fields=["amount_paid", "status", "updated_at"])
