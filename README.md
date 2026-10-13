# AI Billing — Bill Scanner & Ledger App

A smart, responsive web dashboard where you can upload bills (photos, screenshots, PDFs; printed or handwritten).
AI automatically reads the bill, extracts items and totals, tracks shopkeepers (vendors) and customers, organizes spending categories, and maintains a complete payment ledger (khata).

Works in **English** and **Urdu** (with full right-to-left RTL layout) and supports offline manual entries.

---

## 🚀 Quick Start Guide (Windows)

Follow these exact steps in your terminal (PowerShell or Command Prompt):

### Step 1: Open project directory
```powershell
cd d:\projects\aibilling
```
*Navigates to the project folder.*

### Step 2: Install dependencies
```powershell
pip install -r requirements.txt
```
*Installs Django and the required Python libraries.*

### Step 3: Set up environment variables
```powershell
copy .env.example .env
```
*Creates your local settings file with sensible defaults for development.*

### Step 4: Run database migrations
```powershell
python manage.py migrate
```
*Creates all database tables in a local SQLite file (zero database setup needed).*

### Step 5: Create default superadmin
```powershell
python manage.py create_superadmin
```
*Creates a pre-configured developer admin account (username: `admin`, password: `admin`).*

### Step 6: Start the development server
```powershell
python manage.py runserver
```
*Starts your local web server.*

Open your web browser and visit: **http://127.0.0.1:8000**

---

## 🍎 Quick Start Guide (macOS / Linux)

```bash
cd aibilling
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py create_superadmin
python manage.py runserver
```

---

## 🧪 Running Tests & Quality Checks

Run the automated test suite:
```powershell
python -m pytest -q
```

Run test suite with coverage:
```powershell
python -m pytest --cov=. --cov-report=term-missing -q
```

Run linter and formatting checks:
```powershell
python -m ruff check .
python -m ruff format --check .
```

Verify Django system and migration health:
```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
```

---

## 👥 Default Accounts

- **Super Admin:**
  - Username: `admin`
  - Password: `admin`
  - Access: Full control, user management, all reports.

---

## 🗺️ Project Architecture

- `accounts/` — Custom User model, authentication, role permissions (Super Admin vs Staff).
- `bills/` — Bills, line items, and file attachments.
- `parties/` — Vendor and customer profiles with fuzzy auto-matching.
- `ledger/` — Khata ledger statements, payments, and balances.
- `reports/` — Analytics, trends, and repeat purchase tracking.
- `scanning/` — AI document vision extraction pipeline (Gemini / Claude).
- `categories/` — Dynamic categorization and vendor-category mappings.
- `settings_app/` — Shop profile and system configuration.
- `sync/` — Offline sync queue for PWA.
- `templates/` & `static/` — Tailwind CSS + HTMX + Alpine.js frontend.
- `tests/` — Automated test suite adhering to strict quality gates.

---

## 🌐 Deployment (Local, Free Cloud & Live Server)

See the complete, beginner-friendly step-by-step guide in **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**:

1. **Stage 1 — Local Computer:** SQLite + `python manage.py runserver`
2. **Stage 2 — Free Cloud Server:** Render (`render.yaml`, `build.sh`, `Procfile`) + Neon/Supabase Free PostgreSQL
3. **Stage 3 — Live Production VPS:** Ubuntu + Gunicorn (`deploy/gunicorn.service`) + Nginx HTTPS (`deploy/nginx.conf`) + Automated Daily Backups (`deploy/backup_cron.sh`)
- **Healthcheck Endpoint:** `GET /healthz/` returns `{"status": "ok", "database": "connected"}`

