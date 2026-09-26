from django.core.validators import MinValueValidator
from django.db import models

from accounts.models import Client, TimeEntry, User


class Project(models.Model):
    """A body of work for one client."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_HOLD = "on_hold", "On hold"
        DONE = "done", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="projects")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Overrides the client rate for work on this project.",
    )
    budget = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    started_on = models.DateField(null=True, blank=True)
    due_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["owner", "status"])]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="uniq_project_name_per_owner")
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def effective_rate(self) -> float:
        if self.hourly_rate is not None:
            return float(self.hourly_rate)
        return self.client.effective_rate

    @property
    def hours_logged(self) -> float:
        agg = self.time_entries.aggregate(t=models.Sum("hours"))
        return round(float(agg["t"] or 0), 2)

    @property
    def earned(self) -> float:
        agg = self.time_entries.aggregate(t=models.Sum("hours"))
        return round(float(agg["t"] or 0) * self.effective_rate, 2)

    @property
    def budget_remaining(self) -> float | None:
        if self.budget is None:
            return None
        return round(float(self.budget) - self.earned, 2)

    @property
    def is_over_budget(self) -> bool:
        remaining = self.budget_remaining
        return remaining is not None and remaining < 0
