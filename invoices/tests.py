from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Client, TimeEntry
from invoices.models import Invoice, Payment
from projects.models import Project

User = get_user_model()


class ApiTestCase(TestCase):
    """Shared auth helpers."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="devuser",
            email="devuser@example.com",
            password="a-strong-pass-99",
            first_name="Dev",
            last_name="User",
            business_name="Demo Studio",
            hourly_rate=Decimal("75.00"),
        )
        self.other = User.objects.create_user(
            username="mallory", email="mallory@example.com", password="another-pass-77"
        )
        self.client.force_authenticate(self.user)

    def make_client(self, **kwargs):
        defaults = {"owner": self.user, "name": "Acme", "email": "ap@acme.test"}
        defaults.update(kwargs)
        return Client.objects.create(**defaults)


class AuthTests(ApiTestCase):
    def test_register_creates_user_and_hashes_password(self):
        res = APIClient().post(
            reverse("register"),
            {
                "username": "newbie",
                "email": "newbie@example.com",
                "password": "s3cure-long-pass",
                "password_confirm": "s3cure-long-pass",
            },
        )
        self.assertEqual(res.status_code, 201, res.data)
        created = User.objects.get(username="newbie")
        self.assertNotEqual(created.password, "s3cure-long-pass")
        self.assertTrue(created.check_password("s3cure-long-pass"))

    def test_register_rejects_mismatched_passwords(self):
        res = APIClient().post(
            reverse("register"),
            {
                "username": "x",
                "email": "x@example.com",
                "password": "s3cure-long-pass",
                "password_confirm": "different-pass",
            },
        )
        self.assertEqual(res.status_code, 400)

    def test_register_rejects_duplicate_email_case_insensitively(self):
        res = APIClient().post(
            reverse("register"),
            {
                "username": "dupe",
                "email": "DEVUSER@example.com",
                "password": "s3cure-long-pass",
                "password_confirm": "s3cure-long-pass",
            },
        )
        self.assertEqual(res.status_code, 400)

    def test_anonymous_cannot_list_clients(self):
        res = APIClient().get("/api/clients/")
        self.assertEqual(res.status_code, 401)

    def test_healthz_needs_no_auth(self):
        res = APIClient().get("/healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})


class TenantIsolationTests(ApiTestCase):
    """The single most important property in a multi-tenant API."""

    def test_list_only_returns_own_records(self):
        self.make_client(name="Mine")
        Client.objects.create(owner=self.other, name="Theirs")
        res = self.client.get("/api/clients/")
        names = [row["name"] for row in res.data["results"]]
        self.assertEqual(names, ["Mine"])

    def test_cannot_read_another_users_client_by_id(self):
        theirs = Client.objects.create(owner=self.other, name="Theirs")
        res = self.client.get(f"/api/clients/{theirs.id}/")
        self.assertEqual(res.status_code, 404)

    def test_cannot_write_another_users_client_by_id(self):
        theirs = Client.objects.create(owner=self.other, name="Theirs")
        res = self.client.patch(f"/api/clients/{theirs.id}/", {"name": "Hijacked"}, format="json")
        self.assertEqual(res.status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.name, "Theirs")

    def test_cannot_delete_another_users_invoice(self):
        their_client = Client.objects.create(owner=self.other, name="Theirs")
        their_invoice = Invoice.objects.create(
            owner=self.other,
            client=their_client,
            due_on=timezone.localdate() + timedelta(days=7),
        )
        res = self.client.delete(f"/api/invoices/{their_invoice.id}/")
        self.assertEqual(res.status_code, 404)
        self.assertTrue(Invoice.objects.filter(pk=their_invoice.pk).exists())

    def test_cannot_create_invoice_against_another_users_client(self):
        their_client = Client.objects.create(owner=self.other, name="Theirs")
        res = self.client.post(
            "/api/invoices/",
            {"client": their_client.id, "due_on": str(timezone.localdate() + timedelta(days=7))},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("client", res.data["error"]["details"])


class InvoiceMoneyTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.client_acme = self.make_client(name="Acme", hourly_rate=Decimal("100.00"))

    def test_number_is_allocated_sequentially(self):
        first = Invoice.objects.create(
            owner=self.user, client=self.client_acme, due_on=timezone.localdate()
        )
        second = Invoice.objects.create(
            owner=self.user, client=self.client_acme, due_on=timezone.localdate()
        )
        self.assertEqual(first.number, "INV-0001")
        self.assertEqual(second.number, "INV-0002")

    def test_number_does_not_collide_across_accounts(self):
        theirs = Client.objects.create(owner=self.other, name="Theirs")
        mine = Invoice.objects.create(
            owner=self.user, client=self.client_acme, due_on=timezone.localdate()
        )
        other_invoice = Invoice.objects.create(
            owner=self.other, client=theirs, due_on=timezone.localdate()
        )
        self.assertEqual(mine.number, other_invoice.number)

    def test_totals_include_tax_and_discount(self):
        invoice = Invoice.objects.create(
            owner=self.user,
            client=self.client_acme,
            due_on=timezone.localdate(),
            tax_rate=Decimal(18),
            discount=Decimal(100),
        )
        invoice.lines.create(description="Build", quantity=Decimal(10), unit_price=Decimal(100))
        invoice.refresh_from_db()
        self.assertEqual(invoice.subtotal, Decimal("1000.00"))
        self.assertEqual(invoice.tax_amount, Decimal("162.00"))  # (1000 - 100) * 18%
        self.assertEqual(invoice.total, Decimal("1062.00"))  # taxable 900 + tax 162

    def test_discount_cannot_push_taxable_below_zero(self):
        invoice = Invoice.objects.create(
            owner=self.user,
            client=self.client_acme,
            due_on=timezone.localdate(),
            tax_rate=Decimal(18),
            discount=Decimal(5000),
        )
        invoice.lines.create(description="Build", quantity=Decimal(1), unit_price=Decimal(100))
        invoice.refresh_from_db()
        self.assertEqual(invoice.tax_amount, Decimal("0.00"))
        self.assertEqual(invoice.total, Decimal("0.00"))

    def test_payment_settles_invoice(self):
        invoice = Invoice.objects.create(
            owner=self.user, client=self.client_acme, due_on=timezone.localdate()
        )
        invoice.lines.create(description="Work", quantity=Decimal(5), unit_price=Decimal(100))
        invoice.refresh_from_db()
        self.assertEqual(invoice.total, Decimal("500.00"))

        Payment.objects.create(invoice=invoice, amount=Decimal("500.00"))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        self.assertEqual(invoice.balance_due, 0)

    def test_partial_payment_leaves_balance(self):
        invoice = Invoice.objects.create(
            owner=self.user,
            client=self.client_acme,
            status=Invoice.Status.SENT,
            due_on=timezone.localdate(),
        )
        invoice.lines.create(description="Work", quantity=Decimal(5), unit_price=Decimal(100))
        invoice.refresh_from_db()
        Payment.objects.create(invoice=invoice, amount=Decimal("200.00"))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.SENT)
        self.assertEqual(invoice.balance_due, 300)

    def test_overpayment_is_clamped_at_the_model_level(self):
        """Any caller - API, admin, shell - must not create a negative balance."""
        invoice = Invoice.objects.create(
            owner=self.user, client=self.client_acme, due_on=timezone.localdate()
        )
        invoice.lines.create(description="Work", quantity=Decimal(1), unit_price=Decimal(100))
        invoice.refresh_from_db()
        Payment.objects.create(invoice=invoice, amount=Decimal("250.00"))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        self.assertEqual(invoice.balance_due, 0)
        self.assertEqual(invoice.payments.get().amount, Decimal("100.00"))

    def test_paying_a_settled_invoice_raises(self):
        invoice = Invoice.objects.create(
            owner=self.user, client=self.client_acme, due_on=timezone.localdate()
        )
        invoice.lines.create(description="Work", quantity=Decimal(1), unit_price=Decimal(100))
        invoice.refresh_from_db()
        invoice.mark_paid()
        with self.assertRaises(ValueError):
            Payment.objects.create(invoice=invoice, amount=Decimal("10.00"))

    def test_api_rejects_payment_larger_than_balance(self):
        invoice = Invoice.objects.create(
            owner=self.user, client=self.client_acme, due_on=timezone.localdate()
        )
        invoice.lines.create(description="Work", quantity=Decimal(1), unit_price=Decimal(100))
        res = self.client.post(
            f"/api/invoices/{invoice.id}/payments/", {"amount": "5000"}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("amount", res.data["error"]["details"])

    def test_api_rejects_zero_payment(self):
        invoice = Invoice.objects.create(
            owner=self.user, client=self.client_acme, due_on=timezone.localdate()
        )
        invoice.lines.create(description="Work", quantity=Decimal(1), unit_price=Decimal(100))
        res = self.client.post(f"/api/invoices/{invoice.id}/payments/", {"amount": "0"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_is_overdue_uses_due_date_and_status(self):
        invoice = Invoice.objects.create(
            owner=self.user,
            client=self.client_acme,
            status=Invoice.Status.SENT,
            due_on=timezone.localdate() - timedelta(days=10),
        )
        invoice.lines.create(description="Work", quantity=Decimal(1), unit_price=Decimal(100))
        invoice.refresh_from_db()
        self.assertTrue(invoice.is_overdue)
        self.assertEqual(invoice.days_overdue, 10)

    def test_settled_invoice_cannot_be_reopened(self):
        invoice = Invoice.objects.create(
            owner=self.user, client=self.client_acme, due_on=timezone.localdate()
        )
        invoice.lines.create(description="Work", quantity=Decimal(1), unit_price=Decimal(100))
        invoice.refresh_from_db()
        invoice.mark_paid()
        res = self.client.patch(
            f"/api/invoices/{invoice.id}/", {"status": Invoice.Status.SENT}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_duplicate_client_name_rejected(self):
        self.make_client(name="Dupe")
        res = self.client.post(
            "/api/clients/", {"name": "Dupe"}, format="json"
        )
        self.assertEqual(res.status_code, 400)


class TimeEntryTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.client_acme = self.make_client(name="Acme", hourly_rate=Decimal("80.00"))
        self.project = Project.objects.create(owner=self.user, client=self.client_acme, name="Site")

    def test_rate_defaults_to_client_rate(self):
        entry = TimeEntry.objects.create(
            owner=self.user, client=self.client_acme, description="Work", hours=Decimal(2)
        )
        self.assertEqual(entry.hourly_rate, Decimal("80.00"))
        self.assertEqual(entry.amount, 160)

    def test_project_rate_overrides_client_rate(self):
        self.project.hourly_rate = Decimal("120.00")
        self.project.save()
        entry = TimeEntry.objects.create(
            owner=self.user,
            client=self.client_acme,
            project=self.project,
            description="Work",
            hours=Decimal("1.5"),
        )
        self.assertEqual(entry.hourly_rate, Decimal("120.00"))

    def test_rejects_project_from_a_different_client(self):
        other_client = self.make_client(name="Other")
        foreign_project = Project.objects.create(owner=self.user, client=other_client, name="Theirs")
        res = self.client.post(
            "/api/time-entries/",
            {
                "client": self.client_acme.id,
                "project": foreign_project.id,
                "description": "Work",
                "hours": "2",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("project", res.data["error"]["details"])

    def test_rejects_zero_hours(self):
        res = self.client.post(
            "/api/time-entries/",
            {"client": self.client_acme.id, "description": "Work", "hours": "0"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_project_budget_burndown(self):
        TimeEntry.objects.create(
            owner=self.user, client=self.client_acme, project=self.project, description="Work", hours=Decimal(5)
        )
        self.project.budget = Decimal("300.00")
        self.project.save()
        self.assertEqual(self.project.hours_logged, 5)
        self.assertEqual(self.project.earned, 400)  # 5h x client rate 80
        self.assertTrue(self.project.is_over_budget)


class GenerateInvoiceTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.client_acme = self.make_client(name="Acme", hourly_rate=Decimal("100.00"))
        for i in range(3):
            TimeEntry.objects.create(
                owner=self.user,
                client=self.client_acme,
                description=f"Task {i}",
                hours=Decimal(2),
            )

    def test_generate_consumes_unbilled_time(self):
        res = self.client.post(
            "/api/invoices/generate/", {"client": self.client_acme.id, "due_in_days": 14}, format="json"
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["line_items_created"], 3)
        invoice = Invoice.objects.get(pk=res.data["invoice"]["id"])
        self.assertEqual(invoice.total, Decimal("600.00"))
        self.assertEqual(TimeEntry.objects.filter(is_billed=True).count(), 3)

    def test_generate_does_not_double_bill(self):
        self.client.post(
            "/api/invoices/generate/", {"client": self.client_acme.id}, format="json"
        )
        res = self.client.post(
            "/api/invoices/generate/", {"client": self.client_acme.id}, format="json"
        )
        self.assertEqual(res.data["line_items_created"], 0)

    def test_cannot_send_an_empty_invoice(self):
        invoice = Invoice.objects.create(
            owner=self.user, client=self.client_acme, due_on=timezone.localdate()
        )
        res = self.client.post(f"/api/invoices/{invoice.id}/send/")
        self.assertEqual(res.status_code, 400)
        self.assertIn("no line items", res.data["error"]["message"])

    def test_pdf_endpoint_returns_a_pdf(self):
        invoice = Invoice.objects.create(
            owner=self.user, client=self.client_acme, due_on=timezone.localdate()
        )
        invoice.lines.create(description="Build", quantity=Decimal(2), unit_price=Decimal(100))
        res = self.client.get(f"/api/invoices/{invoice.id}/pdf/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertTrue(res.content.startswith(b"%PDF"))


class DashboardTests(ApiTestCase):
    def test_dashboard_aggregates_only_own_data(self):
        mine = self.make_client(name="Mine")
        theirs = Client.objects.create(owner=self.other, name="Theirs")
        Invoice.objects.create(owner=self.user, client=mine, due_on=timezone.localdate())
        Invoice.objects.create(owner=self.other, client=theirs, due_on=timezone.localdate())

        res = self.client.get("/api/dashboard/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["clients"]["total"], 1)
        self.assertEqual([c["name"] for c in res.data["top_clients"]], ["Mine"])
