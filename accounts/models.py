from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """Project owner.

    One account owns exactly one tenant's data: every Client, Project, Invoice
    and TimeEntry is scoped to ``self``. The API enforces that scoping, so a
    user can never read or write another user's records.
    """

    email = models.EmailField(unique=True)
    business_name = models.CharField(max_length=160, blank=True)
    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Default billed hourly rate, used to price time entries.",
    )
    default_currency = models.CharField(max_length=3, default="USD")
    invoice_prefix = models.CharField(
        max_length=8,
        default="INV",
        help_text="Prefix used to build invoice numbers, e.g. INV-0007.",
    )
    next_invoice_seq = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)

    REQUIRED_FIELDS = ["email"]

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.get_full_name() or self.username

    def allocate_invoice_number(self) -> str:
        """Reserve the next invoice number for this account.

        Uses ``select_for_update`` on the user row so two concurrent invoice
        creations can never be handed the same number.
        """
        locked = User.objects.select_for_update().get(pk=self.pk)
        number = f"{locked.invoice_prefix}-{locked.next_invoice_seq:04d}"
        locked.next_invoice_seq += 1
        locked.save(update_fields=["next_invoice_seq"])
        self.next_invoice_seq = locked.next_invoice_seq
        return number

    @property
    def is_accepting_work(self) -> bool:
        return self.clients.filter(is_active=True).exists()


class Client(models.Model):
    """A paying customer of the account."""

    class Status(models.TextChoices):
        LEAD = "lead", "Lead"
        ACTIVE = "active", "Active"
        ON_HOLD = "on_hold", "On hold"
        ARCHIVED = "archived", "Archived"

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="clients")
    name = models.CharField(max_length=160)
    company = models.CharField(max_length=160, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.LEAD)
    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Overrides the account rate for this client when set.",
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
            models.Index(fields=["owner", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="uniq_client_name_per_owner")
        ]

    def __str__(self) -> str:
        return self.company or self.name

    @property
    def effective_rate(self) -> float:
        if self.hourly_rate is not None:
            return float(self.hourly_rate)
        return float(self.owner.hourly_rate or 0)

    @property
    def outstanding_balance(self) -> "Money":
        from invoices.models import Invoice

        agg = Invoice.objects.filter(client=self).aggregate(
            outstanding=models.Sum(
                "total", filter=models.Q(status__in=[Invoice.Status.SENT, Invoice.Status.OVERDUE])
            ),
            paid=models.Sum("amount_paid")
        )
        return Money(
            gross=float(agg["outstanding"] or 0),
            paid=float(agg["paid"] or 0),
        )


class Money:
    """Small value object for invoice money maths.

    Kept deliberately explicit about rounding so the totals a user sees always
    match the totals a client is billed.
    """

    def __init__(self, gross: float = 0.0, paid: float = 0.0) -> None:
        self.gross = round(gross, 2)
        self.paid = round(paid, 2)

    @property
    def balance_due(self) -> float:
        return round(self.gross - self.paid, 2)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Money(gross={self.gross}, paid={self.paid}, due={self.balance_due})"


class TimeEntry(models.Model):
    """Logged work. Becomes invoice line items when billed."""

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="time_entries")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="time_entries")
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="time_entries",
    )
    description = models.CharField(max_length=300)
    hours = models.DecimalField(max_digits=6, decimal_places=2)
    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Rate snapshotted at log time so later rate changes do not rewrite history.",
    )
    logged_on = models.DateField(default=timezone.localdate)
    is_billed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-logged_on", "-created_at"]
        indexes = [models.Index(fields=["owner", "-logged_on"])]

    def __str__(self) -> str:
        return f"{self.hours}h {self.description[:40]}"

    @property
    def amount(self) -> float:
        return round(float(self.hours) * float(self.hourly_rate), 2)

    def save(self, *args, **kwargs):
        if not self.hourly_rate:
            # Project rate wins over client rate; client rate wins over the
            # account default. Resolved once, at log time, so later rate changes
            # never rewrite what was already earned.
            if self.project_id:
                self.hourly_rate = self.project.effective_rate
            else:
                self.hourly_rate = self.client.effective_rate
        super().save(*args, **kwargs)
