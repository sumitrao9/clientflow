"""Populate the database with realistic demo data.

    python manage.py seed_demo --reset

Useful for screenshots, for demoing to a client, and for eyeballing the
dashboard without hand-entering an hour of data.
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Client, TimeEntry
from invoices.models import Invoice, Payment
from projects.models import Project

User = get_user_model()

CLIENTS = [
    ("Northwind Retail", "Priya Raman", "priya@northwind.example", Client.Status.ACTIVE, 95),
    ("Halcyon Labs", "Daniel Osei", "daniel@halcyon.example", Client.Status.ACTIVE, 120),
    ("Brightline Health", "Sara Iqbal", "sara@brightline.example", Client.Status.ACTIVE, 110),
    ("Kettle & Co", "Marcus Lind", "marcus@kettleco.example", Client.Status.LEAD, 75),
    ("Orbit Logistics", "Fatima Noor", "fatima@orbitlog.example", Client.Status.ON_HOLD, 90),
]

PROJECTS = {
    "Northwind Retail": [
        ("Storefront replatform", "Migrate the legacy storefront to a Django + React stack.", 6000),
        ("Checkout performance audit", "Profile and fix checkout latency.", 2400),
    ],
    "Halcyon Labs": [
        ("REST API for internal analytics", "Token-authenticated reporting API.", 8000),
    ],
    "Brightline Health": [
        ("Patient booking portal", "Scheduling with role-based access.", 9500),
    ],
    "Kettle & Co": [
        ("Marketing site build", "Five-page marketing site on a CMS.", 3000),
    ],
    "Orbit Logistics": [
        ("Fleet dashboard", "Live fleet tracking dashboard.", 7000),
    ],
}

TASKS = [
    "Implemented REST endpoints for the reporting module",
    "Fixed N+1 queries on the dashboard aggregation",
    "Built responsive invoice list UI",
    "Wrote unit tests for the permission layer",
    "Refactored the legacy view into a class-based view",
    "Added CSV export for the admin team",
    "Reviewed pull requests and gave feedback",
    "Set up CI to run the test suite on every push",
    "Debugged a timezone bug in the daily digest email",
    "Wrote the API documentation and onboarding guide",
    "Optimised image pipeline for the media gallery",
    "Migrated the project to the new settings layout",
    "Pair-programmed on the payment webhook handler",
    "Added pagination and filtering to the list endpoints",
]


class Command(BaseCommand):
    help = "Seed demo clients, projects, time entries and invoices."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing data first.")
        parser.add_argument("--username", default="demo", help="Account to create or reuse.")

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(20260826)  # deterministic demo data

        if options["reset"]:
            Payment.objects.all().delete()
            Invoice.objects.all().delete()
            TimeEntry.objects.all().delete()
            Project.objects.all().delete()
            Client.objects.all().delete()
            self.stdout.write(self.style.WARNING("Cleared existing data."))

        user, created = User.objects.get_or_create(
            username=options["username"],
            defaults={
                "email": "demo@clientflow.example",
                "first_name": "Demo",
                "last_name": "User",
                "business_name": "Demo Studio",
                "hourly_rate": Decimal("75.00"),
                "default_currency": "USD",
                "invoice_prefix": "INV",
            },
        )
        if created:
            user.set_password("demo-pass-1234")
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f"Created user '{user.username}' (demo-pass-1234)")
            )
        else:
            self.stdout.write(f"Reusing user '{user.username}'")

        clients = []
        for name, _contact, email, status, rate in CLIENTS:
            client, _ = Client.objects.get_or_create(
                owner=user,
                name=name,
                defaults={
                    "company": name,
                    "email": email,
                    "phone": f"+1 555 01{rng.randint(10, 99)}",
                    "status": status,
                    "hourly_rate": Decimal(rate),
                    "is_active": status != Client.Status.ARCHIVED,
                },
            )
            clients.append(client)
        self.stdout.write(f"{len(clients)} clients ready")

        projects = []
        for client in clients:
            for name, desc, budget in PROJECTS.get(client.name, []):
                project, _ = Project.objects.get_or_create(
                    owner=user,
                    name=name,
                    defaults={
                        "client": client,
                        "description": desc,
                        "budget": Decimal(budget),
                        "started_on": timezone.localdate() - timedelta(days=rng.randint(20, 90)),
                        "due_on": timezone.localdate() + timedelta(days=rng.randint(5, 60)),
                    },
                )
                projects.append(project)
        self.stdout.write(f"{len(projects)} projects ready")

        entries = []
        for _ in range(70):
            project = rng.choice(projects)
            hours = Decimal(str(round(rng.uniform(0.5, 7.5), 2)))
            entries.append(
                TimeEntry(
                    owner=user,
                    client=project.client,
                    project=project,
                    description=rng.choice(TASKS),
                    hours=hours,
                    hourly_rate=project.effective_rate,
                    logged_on=timezone.localdate() - timedelta(days=rng.randint(1, 75)),
                )
            )
        TimeEntry.objects.bulk_create(entries)
        self.stdout.write(f"{len(entries)} time entries logged")

        invoices = []
        for client in clients:
            for issued_days_ago, status in [
                (62, Invoice.Status.PAID),
                (34, Invoice.Status.PAID),
                (12, Invoice.Status.SENT),
            ]:
                invoice = Invoice.objects.create(
                    owner=user,
                    client=client,
                    project=rng.choice([p for p in projects if p.client_id == client.id] or [None]),
                    status=status,
                    issued_on=timezone.localdate() - timedelta(days=issued_days_ago),
                    due_on=timezone.localdate() - timedelta(days=issued_days_ago - 14),
                    tax_rate=Decimal(0),
                )
                for _ in range(rng.randint(2, 5)):
                    hours = Decimal(str(round(rng.uniform(1, 8), 2)))
                    invoice.lines.create(
                        description=rng.choice(TASKS),
                        quantity=hours,
                        unit_price=Decimal(str(client.effective_rate)),
                    )
                invoice.recalculate()
                invoice.save()

                if status == Invoice.Status.PAID:
                    Payment.objects.create(
                        invoice=invoice,
                        amount=invoice.total,
                        method=rng.choice(["bank_transfer", "card", "paypal"]),
                        reference=f"PMT-{rng.randint(10000, 99999)}",
                        received_on=invoice.due_on - timedelta(days=rng.randint(0, 5)),
                    )
                invoices.append(invoice)

        self.stdout.write(self.style.SUCCESS(f"{len(invoices)} invoices created"))

        # One deliberately overdue invoice so the dashboard's overdue panel is non-empty.
        stale = Invoice.objects.filter(owner=user, status=Invoice.Status.SENT).first()
        if stale:
            stale.issued_on = timezone.localdate() - timedelta(days=75)
            stale.due_on = timezone.localdate() - timedelta(days=40)
            stale.save()
            self.stdout.write(f"  {stale.number} marked overdue for demo purposes")

        self.stdout.write(self.style.SUCCESS("Seed complete."))
