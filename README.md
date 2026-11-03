# ClientFlow

**Production-grade REST API for freelance invoicing with bulletproof financial integrity.**

[![CI](https://github.com/sumitrao9/clientflow/actions/workflows/ci.yml/badge.svg)](https://github.com/sumitrao9/clientflow/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Django](https://img.shields.io/badge/Django-5-092e20)
![DRF](https://img.shields.io/badge/DRF-3.15-ff1709)

## Problem

Most freelance invoicing tools are built as CRUD apps with business logic scattered across views and serializers. This leads to real money bugs: incorrect totals, double-billed hours, invoices edited after payment, and cross-tenant data leaks.

## Solution

ClientFlow enforces **financial correctness at the model layer** - if it can't be guaranteed by the database and business rules, it won't happen. Built with Django 5, DRF, and tested with **33 tests**.

## Key Features

| Feature | Why It Matters |
| --- | --- |
| **Financial Invariants** | Payments clamp to outstanding balance. Discounts can't create negative taxes. Totals recalculate atomically. |
| **Row-Level Invoice Numbering** | Invoice numbers allocated under `select_for_update()` per account - impossible to get duplicates even under concurrency. |
| **Immutable Settled Invoices** | Paid or void invoices cannot be modified. Prevents re-billing or tampering with paid work. |
| **Two-Layer Multi-Tenancy** | Queryset scoping + object-level permission re-checks. Another user's data is unreadable, unwritable, and undeletable. |
| **Time Tracking with Snapshots** | Hourly rates snapshotted at log time - rate changes never rewrite historical billing. |
| **Automatic Invoice Generation** | Generate invoices from unbilled time entries with one click. |
| **PDF Generation** | Professional PDF invoices via ReportLab. |
| **Receivables Dashboard** | Real-time view of who owes what, with overdue tracking. |

## Try It Live

> *[Deploy to Render/Railway and add live URL here]*

- **API Docs (Swagger):** `/api/docs/`
- **OpenAPI Schema:** `/api/schema/`
- **Health Check:** `/healthz`

**Demo credentials:** `demo` / `demo-pass-1234` (after running seed data)

## Tech Stack

`Django 5` `Django REST Framework` `PostgreSQL` `JWT Auth` `ReportLab` `Docker` `drf-spectacular` `Gunicorn` `WhiteNoise`

## Quick Start

### Local Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo --reset
python manage.py runserver
```

API docs at [http://127.0.0.1:8000/api/docs/](http://127.0.0.1:8000/api/docs/)

### Docker

```bash
docker compose up --build
```

## API Overview

```http
GET    /api/clients/              List/manage clients
GET    /api/projects/            List/manage projects
GET    /api/time-entries/        Log trackable time
POST   /api/invoices/generate/   Generate from unbilled time
POST   /api/invoices/{id}/send/  Mark as sent
POST   /api/invoices/{id}/payments/ Record payment
GET    /api/invoices/{id}/pdf/   Download PDF
GET    /api/invoices/receivables/ Outstanding balances
GET    /api/dashboard/           Business overview
```

## Testing

```bash
python manage.py test
```

**33 tests** covering money maths, tax/discount edge cases, invoice numbering collisions, payment clamping, settled-invoice immutability, multi-tenant isolation, PDF generation, and dashboard aggregation. Runs in ~50 seconds with SQLite, no external services needed.

## Security

- Refuses boot with `DEBUG=False` and default secret key
- Auto-enables security headers, HSTS, secure cookies in production
- Consistent error envelope across all endpoints
- Rate-limited auth endpoints
- `IntegrityError` caught and sanitized (no schema leakage)

## Deployment

Ready to deploy on **Render** or **Railway** with included `Dockerfile`, `render.yaml`, and `Procfile`.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

## License

MIT License - see [LICENSE](LICENSE) for details.
