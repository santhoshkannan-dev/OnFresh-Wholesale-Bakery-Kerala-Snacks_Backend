# OnFresh-Wholesale-Bakery-Kerala-Snacks_Backend

**OnFresh** — Wholesale Bakery & Traditional Kerala Snacks (Vandiperiyar, Idukki, Kerala, India).

Backend REST API service built with **Python 3.12+**, **Django 5**, **Django REST Framework (DRF)**, and **PostgreSQL**.

---

## Architecture & Modular Apps

- `apps.core`: Custom User model, Base models, Audit logging, System configuration.
- `apps.products`: Category & product catalogue, variants, stock units, images.
- `apps.customers`: B2C retail & B2B wholesale profiles, address management, wholesale approval workflow.
- `apps.orders`: Cart, server-side pricing engine (`PricingService`), multi-step checkout, order state machine, GST invoices.
- `apps.inventory`: Real-time stock tracking, batch-level movements, expiry tracking, stock-in/adjustment workflows.
- `apps.manufacturing`: Bill of Materials (BOM) recipes, production batches, quality assurance, raw materials, supplier management.
- `apps.analytics`: Executive KPI dashboards, sales metrics, customer segmentation, automated reports.

---

## Tech Stack

- **Framework:** Django 5 & Django REST Framework
- **Database:** PostgreSQL
- **Authentication:** JWT via `djangorestframework-simplejwt`
- **CORS:** `django-cors-headers`
- **Testing:** Comprehensive Django test suite (83+ unit/integration tests)

---

## Getting Started

### 1. Setup Virtual Environment
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Ensure PostgreSQL connection parameters (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`) are populated.

### 4. Run Migrations & Tests
```bash
python manage.py migrate
python manage.py test apps.core apps.products apps.customers apps.orders apps.inventory apps.analytics apps.manufacturing
```

### 5. Start Development Server
```bash
python manage.py runserver 8000
```
API endpoints available at `http://localhost:8000/api/`.
