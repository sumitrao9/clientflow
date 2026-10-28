# ClientFlow

**A REST API for freelance client management, time tracking, and invoicing.**

[![CI](https://github.com/sumitrao9/clientflow/actions/workflows/ci.yml/badge.svg)](https://github.com/sumitrao9/clientflow/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Django](https://img.shields.io/badge/Django-5-092e20)

Most freelancers track hours in a spreadsheet and invoice from a template. This is the API
underneath a real replacement: log time against clients and projects, generate an invoice from
unbilled hours, send it, and record payments — with the money maths enforced server-side so the
number the client sees always matches the number you meant.

Built with Django 5 and Django REST Framework, tested with 33 tests, and ships with Docker,
PostgreSQL, and CI.

---

## Why it exists

Two things go wrong with hand-rolled freelance invoicing, and both are money bugs:

1. **The total is wrong.** Discounts and tax interact in a way that is easy to get subtly
   wrong, and the error is discovered by the client, not by you.
2. **Time gets billed twice.** A partially-billed hour reappears on the next invoice.

Both are handled here as invariants, not as things to be careful about.

## What it does

| Area | Behaviour |
|---|---|
| **Clients** | Leads, active, on hold, archived. Per-client hourly rate with account-level fallback. |
| **Projects** | Budget, burn-down, `is_over_budget`, start/due dates. Per-project rate override. |
| **Time entries** | Rate is snapshotted at log time, so a later rate change never rewrites history. |
| **Invoices** | Auto-numbered per account, line items generated from unbilled time, PDF output. |
| **Payments** | Partial and full, with the invoice settling automatically at zero balance. |
| **Receivables** | Who owes what, grouped by client, with overdue tracking. |
| **Dashboard** | One request: outstanding, collected, overdue, hours logged, recent activity. |

### Money maths

```
subtotal = sum(line.amount)
taxable  = max(subtotal - discount, 0)
tax      = taxable * tax_rate / 100
total    = taxable + tax
```

`taxable` is clamped at zero, so a discount larger than the subtotal produces a zero-tax invoice
rather than a negative one. Totals are recalculated and stored on every write, so list endpoints
never walk line items.

### Invariants enforced in the model, not just the API

- **Invoice numbers cannot collide.** Allocated from the owning user row under
  `select_for_update`, so two concurrent requests cannot be handed the same number. Numbers are
  scoped per account, so your `INV-0001` never collides with anyone else's.
- **Editing a line item re-syncs the invoice.** Adding, changing or deleting a line updates the
  parent totals immediately, rather than waiting for the next invoice save.
- **A payment can never exceed the balance.** Clamped in `Payment.save`, so no caller — API,
  admin, shell, management command — can produce a negative `balance_due`.
- **A settled invoice cannot be reopened.** Paid or void invoices are immutable, so already-paid
  work cannot be re-billed. Duplicate instead.

## Multi-tenancy

Every record is scoped to its owner, and the scoping is enforced in two independent places:

1. Every queryset is filtered to `request.user`.
2. A `IsOwner` object permission re-checks on every object access, and walks one level of
   nesting for models that hang off a `Client` or `Invoice`.

The first is the fast path; the second is what stops an IDOR bug when a record is fetched by id
through some other route. The test suite asserts the isolation directly — another user's client is
invisible, unwritable, and undeletable, and an invoice cannot be created against another user's
client.

## API

All endpoints require a JWT bearer token except registration and `healthz`.

```
POST   /api/auth/register/
POST   /api/auth/token/
POST   /api/auth/token/refresh/
GET    /api/auth/me/
POST   /api/auth/password/
GET    /api/dashboard/

GET    /api/clients/               ?search= &status= &is_active=
POST   /api/clients/
GET    /api/clients/{id}/summary/          aggregated client detail
POST   /api/clients/{id}/archive/

GET    /api/projects/              ?search= &status= &client=
GET    /api/projects/{id}/progress/       budget burn-down
POST   /api/projects/{id}/log_time/

GET    /api/invoices/              ?search= &status= &overdue= &client=
POST   /api/invoices/                      create ad-hoc
POST   /api/invoices/generate/              from unbilled time
POST   /api/invoices/{id}/send/
POST   /api/invoices/{id}/payments/
POST   /api/invoices/{id}/void/
GET    /api/invoices/{id}/pdf/
GET    /api/invoices/receivables/

GET    /api/time-entries/          ?unbilled= &client=

GET    /api/schema/                OpenAPI
GET    /api/docs/                  Swagger UI
GET    /healthz
```

### Error format

Every error, from a serialiser, a permission check, or a hand-written guard, uses one envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Please correct the highlighted fields.",
    "details": { "client": ["Unknown client."] }
  }
}
```

Without this, DRF returns three different shapes depending on where the error came from and
clients end up writing three parsers.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo --reset     # realistic demo data
python manage.py runserver
```

API docs at <http://127.0.0.1:8000/api/docs/>, admin at `/admin/`.

With Docker:

```bash
docker compose up --build
```

`seed_demo` creates a `demo` account (password `demo-pass-1234`) with 5 clients, 5 projects, 70
time entries and 15 invoices, including one deliberately overdue so the dashboard's overdue
panel is not empty.

## Tests

```bash
python manage.py test
```

33 tests covering money maths, tax and discount interaction, invoice numbering and collision,
payment clamping, settled-invoice immutability, multi-tenant isolation (including the negative
cases), extraction and PDF generation, and the dashboard aggregation. The suite runs in about 50
seconds and needs no external services when using SQLite.

## Security notes

- Refuses to boot with `DJANGO_DEBUG=0` and the bundled development secret key, so a
  forgot-to-set-an-env-var cannot become an incident.
- Security headers, HSTS, secure cookies and `X-Frame-Options: DENY` switch on automatically
  when `DEBUG` is off.
- `IntegrityError` is caught and returned as a 409 with a generic message; the raw constraint
  text is logged but never returned, because it discloses schema.
- Auth endpoints are throttled (`20/hour` login, `10/hour` registration).

## Licence

MIT
