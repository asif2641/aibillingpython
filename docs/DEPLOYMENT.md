# AI Billing — Complete Beginner-Friendly Deployment Guide

This guide walks you through running and hosting **AI Billing (Bill Scanner & Ledger)** across all three deployment stages, written for complete beginners with no prior server or database experience.

Every command below can be copied and pasted directly into your terminal, with a one-sentence explanation of what it does.

---

## Table of Contents

1. [Stage 1: Running on Your Local Computer](#stage-1-running-on-your-local-computer)
2. [Stage 2: Deploying to a Free Cloud Server (Render + Neon PostgreSQL)](#stage-2-deploying-to-a-free-cloud-server-render--neon-postgresql)
3. [Stage 3: Deploying to Vercel (Serverless Cloud)](#stage-3-deploying-to-vercel-serverless-cloud)
4. [Stage 4: Deploying to a Live Production Server (Ubuntu VPS)](#stage-4-deploying-to-a-live-production-server-ubuntu-vps)
5. [Environment Variables Reference](#environment-variables-reference)
6. [Troubleshooting Common Issues](#troubleshooting-common-issues)

---

## Stage 1: Running on Your Local Computer

Running the app locally means it runs on your own laptop or desktop computer using **SQLite** (a single file database that requires zero extra software).

### A. Windows (PowerShell)

1. **Open your project folder:**
   ```powershell
   cd d:\projects\aibilling
   ```
   *Moves your terminal into the project folder where `manage.py` lives.*

2. **Create a Python virtual environment (first time only):**
   ```powershell
   python -m venv .venv
   ```
   *Creates an isolated folder (`.venv`) so this app's packages don't conflict with other programs on your computer.*

3. **Activate the virtual environment:**
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
   *Turns on the isolated Python environment for your current terminal window.*

4. **Install all required Python packages:**
   ```powershell
   pip install -r requirements.txt
   ```
   *Downloads and installs Django, Pillow, and all libraries listed in `requirements.txt`.*

5. **Create your `.env` configuration file (first time only):**
   ```powershell
   copy .env.example .env
   ```
   *Copies the starter settings template into `.env` where you can paste your `GEMINI_API_KEY`.*

6. **Compile English & Urdu translation files:**
   ```powershell
   python scripts/compile_mo.py
   ```
   *Compiles the Urdu (`ur`) and English (`en`) translation files so the language switcher works.*

7. **Create the database tables:**
   ```powershell
   python manage.py migrate
   ```
   *Sets up all database tables (bills, vendors, customers, ledger, settings) inside `db.sqlite3`.*

8. **Create the default Super Admin account:**
   ```powershell
   python manage.py create_superadmin
   ```
   *Creates the administrator login (`admin` / `admin`) so you can sign in immediately.*

9. **Start the local web server:**
   ```powershell
   python manage.py runserver
   ```
   *Starts the application on your computer at `http://127.0.0.1:8000`.*

Open your browser and go to **http://127.0.0.1:8000**.

---

### B. macOS / Linux (Terminal)

```bash
cd /path/to/aibilling
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/compile_mo.py
python manage.py migrate
python manage.py create_superadmin
python manage.py runserver
```

---

## Stage 2: Deploying to a Free Cloud Server (Render + Neon PostgreSQL)

In Stage 2, you put the app on the internet for free so you and your staff can open it from any phone or computer.
We use:
- **Neon.tech** (or **Supabase**) for a free cloud **PostgreSQL** database (where your bills and ledger are safely stored).
- **Render.com** for a free cloud **Web Service** (which runs the Python Django app).

### Step 1: Create a Free PostgreSQL Database on Neon.tech

1. Go to [https://neon.tech](https://neon.tech) and sign up for a free account.
2. Click **"New Project"**, name it `aibilling`, and click **Create**.
3. On your Neon dashboard, find the **Connection String** box. It looks like this:
   ```text
   postgresql://neondb_owner:AbCdEf123456@ep-cool-darkness-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
4. Click **Copy** — this is your `DATABASE_URL`. Keep it ready for Step 2.

*(Alternative: You can also use [https://supabase.com](https://supabase.com) → Project Settings → Database → Connection string → URI).*

### Step 2: Push Your Code to GitHub

Render deploys your app directly from a GitHub repository (can be a **Private** repository).

1. Create a new repository on [https://github.com/new](https://github.com/new) named `aibilling`.
2. Push your code to GitHub.

### Step 3: Deploy on Render.com Using Blueprint (`render.yaml`)

This project already includes `render.yaml`, `build.sh`, and `Procfile` at the root folder, which configure Render automatically.

1. Sign up or log in at [https://render.com](https://render.com).
2. Click **"New +"** in the top bar and select **"Blueprint"** (or **"Web Service"**).
3. Connect your GitHub account and select your `aibilling` repository.
4. When prompted for environment variables, paste:
   - `DATABASE_URL`: Paste the PostgreSQL connection string from Neon (Step 1).
   - `GEMINI_API_KEY`: Paste your free Google Gemini API key from [https://aistudio.google.com](https://aistudio.google.com).
5. Click **Apply / Create Web Service**.
6. Render will automatically run `./build.sh` (which installs packages, compiles Urdu translations, collects static files, and runs database migrations) and verify health at `/healthz/`.

### Step 4: Create Your Super Admin Account on Render

Once your service says **Live**, create your login account:

- **Option A (Render Shell):** Go to your Render service dashboard → **Shell** tab, and run:
  ```bash
  python manage.py createsuperuser
  ```
  *Prompts you to choose a username, email, and strong password for your Super Admin account.*

- **Option B (From your local computer connected to the cloud database):**
  ```powershell
  $env:DATABASE_URL="postgresql://your-neon-connection-string"
  python manage.py createsuperuser
  ```
  *Connects temporarily from your computer to your cloud database to create your admin user.*

---

## Stage 3: Deploying to Vercel (Serverless Cloud)

Vercel allows you to host the AI Billing application as a serverless web application with zero server maintenance, automatic SSL, and instant global CDN delivery.

> [!IMPORTANT]
> **Vercel Ephemeral Filesystem & Database:**
> Vercel functions run in a read-only, serverless environment. An external PostgreSQL database (e.g., [Neon](https://neon.tech) or [Supabase](https://supabase.com) — both offer free tiers) is required so your bills, parties, and ledger data are permanently saved. If `DATABASE_URL` is not set, the app temporarily uses `/tmp/db.sqlite3` which resets when serverless containers cycle.

### Step 1: Push Code to GitHub

Your code is already structured for Vercel with:
- `vercel.json`: Directs incoming web requests to the Django WSGI application and static build outputs.
- `build_files.sh`: Automatically runs `pip install` and `collectstatic` during Vercel's build step.
- `api/index.py` & `aibilling/wsgi.py`: WSGI entrypoints configured for the Vercel Python runtime.

Ensure your code is pushed to your GitHub repository:
```bash
git push origin main
```

### Step 2: Create a Free PostgreSQL Database on Neon (2 minutes)

1. Go to **[neon.tech](https://neon.tech)** and sign up with GitHub.
2. Click **Create Project**, name it `aibilling-db`, and choose your nearest region.
3. On the project dashboard, copy the **Connection details** connection string (`postgres://...` or `postgresql://...`).

### Step 3: Connect and Deploy on Vercel

1. Log in to **[vercel.com](https://vercel.com)** using your GitHub account.
2. On your Vercel Dashboard, click **Add New...** → **Project**.
3. Locate `aibillingpython` (or `asif2641/aibillingpython`) in the list of repositories and click **Import**.
4. In the project configuration:
   - **Framework Preset**: Select **Other**.
   - **Root Directory**: `./` (leave default).
   - **Build and Output Settings**: Leave default (overridden by `vercel.json` and `build_files.sh`).
5. Open the **Environment Variables** section and add the following keys:

| Name | Example Value | Description |
|------|---------------|-------------|
| `DJANGO_SETTINGS_MODULE` | `aibilling.settings.production` | Enables production security & WhiteNoise |
| `SECRET_KEY` | *(A long random 50-character string)* | Production cryptographic key |
| `DEBUG` | `False` | Disables debug mode in production |
| `BUILD_MODE` | `True` | Allows `collectstatic` to run safely during build |
| `DATABASE_URL` | `postgresql://user:pass@ep-xyz.neon.tech/neondb?sslmode=require` | Your Neon PostgreSQL connection string |
| `GEMINI_API_KEY` | `AIzaSy...` | Your Google Gemini API key for bill OCR |

6. Click **Deploy**.
7. Vercel will install dependencies, collect static files, and deploy your application. In ~1–2 minutes, you will receive a live URL:
   `https://aibillingpython.vercel.app` (or similar).

### Step 4: Run Initial Database Migrations & Create Super Admin

Since Vercel runs serverless functions without an interactive shell, apply migrations to your cloud database from your computer:

```powershell
# In PowerShell:
$env:DATABASE_URL="postgresql://user:pass@ep-xyz.neon.tech/neondb?sslmode=require"
python manage.py migrate
python manage.py create_superadmin
```

Your admin login (`admin` / `admin`) is now ready on your live Vercel URL!

---

## Stage 4: Deploying to a Live Production Server (Ubuntu VPS)

When your shop grows and you want zero cold-starts, your own custom domain (e.g. `billing.yourshop.com`), local SSD storage for uploaded bill images, and automated daily backups, deploy to a low-cost Ubuntu 22.04 / 24.04 VPS (DigitalOcean, Hetzner, Linode, or AWS Lightsail — typically $4–$6/month).

All configuration templates are ready in the `deploy/` folder:
- `deploy/gunicorn.service` — Keeps the Python app running 24/7 and restarts it automatically if the server reboots.
- `deploy/nginx.conf` — High-speed web server that handles HTTPS encryption and serves images/CSS.
- `deploy/backup_cron.sh` — Runs every night at 2:00 AM to back up your database and clean up old sync records.

### Step 1: Connect to Your Server & Install System Packages

Connect to your server via SSH and run:

```bash
sudo apt update && sudo apt upgrade -y
```
*Updates Ubuntu's package list and installs the latest security patches.*

```bash
sudo apt install -y python3 python3-venv python3-pip postgresql postgresql-contrib nginx certbot python3-certbot-nginx git
```
*Installs Python 3, PostgreSQL database, Nginx web server, Certbot (for free HTTPS certificates), and Git.*

### Step 2: Create the Production PostgreSQL Database

```bash
sudo -u postgres psql -c "CREATE USER aibilling_user WITH PASSWORD 'CHANGE_THIS_STRONG_PASSWORD';"
```
*Creates a dedicated PostgreSQL database user for the application.*

```bash
sudo -u postgres psql -c "CREATE DATABASE aibilling_db OWNER aibilling_user;"
```
*Creates the production database owned by `aibilling_user`.*

### Step 3: Clone the Project & Install Dependencies

```bash
sudo mkdir -p /var/www/aibilling
sudo chown -R $USER:$USER /var/www/aibilling
```
*Creates the `/var/www/aibilling` directory and gives your user permission to write to it.*

```bash
git clone https://github.com/YOUR_USERNAME/aibilling.git /var/www/aibilling
cd /var/www/aibilling
```
*Downloads your application code into `/var/www/aibilling`.*

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```
*Creates the virtual environment and installs all Python dependencies including Gunicorn.*

### Step 4: Configure the Production `.env` File

Create `/var/www/aibilling/.env`:

```bash
cp .env.example .env
nano .env
```
*Creates `.env` and opens the Nano text editor so you can enter your production secrets.*

Set these values inside `/var/www/aibilling/.env`:

```ini
DJANGO_SETTINGS_MODULE=aibilling.settings.production
SECRET_KEY=paste-a-50-character-random-secret-key-here
DEBUG=False
ALLOWED_HOSTS=billing.example.com,www.billing.example.com
CSRF_TRUSTED_ORIGINS=https://billing.example.com,https://www.billing.example.com
DATABASE_URL=postgresql://aibilling_user:CHANGE_THIS_STRONG_PASSWORD@localhost:5432/aibilling_db
GEMINI_API_KEY=your-gemini-api-key
AI_PROVIDER=gemini
```

*(Tip: Generate a secure `SECRET_KEY` anytime by running: `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`)*

### Step 5: Run Migrations, Compile Translations & Collect Static Files

```bash
python scripts/compile_mo.py
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py createsuperuser
```
*Compiles Urdu/English translations, gathers static assets into `staticfiles/`, creates database tables, and prompts you to create your Super Admin login.*

Set ownership so the web server (`www-data`) can read/write media and backup files:

```bash
sudo mkdir -p /var/www/aibilling/media /var/www/aibilling/backups
sudo chown -R www-data:www-data /var/www/aibilling
sudo chmod 600 /var/www/aibilling/.env
```
*Grants the web server access to uploaded bill photos and backups while locking `.env` so only the service can read it.*

### Step 6: Set Up Gunicorn Systemd Service (`deploy/gunicorn.service`)

```bash
sudo cp /var/www/aibilling/deploy/gunicorn.service /etc/systemd/system/gunicorn.service
sudo systemctl daemon-reload
sudo systemctl enable --now gunicorn
```
*Installs and starts the Gunicorn background service so your app runs continuously and starts automatically on reboot.*

Check that Gunicorn is running cleanly:

```bash
sudo systemctl status gunicorn
```
*Displays `active (running)` if Gunicorn started properly.*

### Step 7: Set Up Nginx & Free HTTPS with Let's Encrypt (`deploy/nginx.conf`)

1. Copy the Nginx config and replace `billing.example.com` with your actual domain name:
   ```bash
   sudo cp /var/www/aibilling/deploy/nginx.conf /etc/nginx/sites-available/aibilling
   sudo sed -i 's/billing.example.com/YOUR_DOMAIN.COM/g' /etc/nginx/sites-available/aibilling
   ```
   *Copies the Nginx site config and replaces the example domain with your real domain.*

2. Enable the site and obtain a free Let's Encrypt SSL certificate:
   ```bash
   sudo ln -sf /etc/nginx/sites-available/aibilling /etc/nginx/sites-enabled/
   sudo rm -f /etc/nginx/sites-enabled/default
   sudo certbot --nginx -d YOUR_DOMAIN.COM
   ```
   *Activates the Nginx configuration and automatically issues and configures a free HTTPS certificate from Let's Encrypt.*

3. Verify and reload Nginx:
   ```bash
   sudo nginx -t && sudo systemctl reload nginx
   ```
   *Tests the Nginx configuration for syntax errors and reloads the web server.*

### Step 8: Enable Daily Automated Backups (`deploy/backup_cron.sh`)

1. Make the backup script executable:
   ```bash
   sudo chmod +x /var/www/aibilling/deploy/backup_cron.sh
   ```
   *Marks the backup script as an executable program.*

2. Schedule it to run every night at 2:00 AM under the `www-data` user:
   ```bash
   (sudo crontab -u www-data -l 2>/dev/null; echo "0 2 * * * /var/www/aibilling/deploy/backup_cron.sh >> /var/log/aibilling_backup.log 2>&1") | sudo crontab -u www-data -
   ```
   *Registers a daily cron job at 2:00 AM that creates a JSON database backup (keeping 30 days of history) and purges old sync queue logs.*

---

## Environment Variables Reference

| Variable | Required in Prod? | Default (Local) | Purpose |
|----------|-------------------|-----------------|---------|
| `DJANGO_SETTINGS_MODULE` | **Yes** | `aibilling.settings.local` | Set to `aibilling.settings.production` on Render and VPS servers. |
| `SECRET_KEY` | **Yes** | *(dev fallback)* | Cryptographic key used to sign session cookies and CSRF tokens. Must be unique in production. |
| `DEBUG` | **Yes** | `True` | Must be `False` in production so error tracebacks are never shown to visitors. |
| `ALLOWED_HOSTS` | **Yes** | `localhost,127.0.0.1` | Comma-separated list of domain names allowed to serve the app (auto-includes `RENDER_EXTERNAL_HOSTNAME` on Render). |
| `CSRF_TRUSTED_ORIGINS` | Recommended | *(empty)* | Comma-separated list of `https://yourdomain.com` URLs allowed to submit forms (auto-includes Render HTTPS URL). |
| `DATABASE_URL` | **Yes** (Cloud/VPS) | SQLite (`db.sqlite3`) | PostgreSQL connection URL (`postgres://...` or `postgresql://...`, supports `?sslmode=require`). |
| `GEMINI_API_KEY` | Yes (for AI scan) | *(empty)* | Google Gemini API key for reading printed and handwritten bills. |
| `CLAUDE_API_KEY` | Optional | *(empty)* | Anthropic Claude API key if `AI_PROVIDER=claude`. |
| `AI_PROVIDER` | No | `gemini` | Choose `gemini` or `claude` for bill extraction. |
| `BACKUP_DIR` | No | `<BASE_DIR>/backups` | Custom directory path where `backup_db` stores JSON backups. |
| `DAILY_SCAN_LIMIT` | No | `50` | Maximum AI bill scans allowed per user per day. |
| `MONTHLY_SCAN_LIMIT` | No | `500` | Maximum AI bill scans allowed per user per month. |

---

## Troubleshooting Common Issues

1. **`ImproperlyConfigured: SECRET_KEY must be set to a unique secret value in production.`**
   - **Cause:** You are running with `aibilling.settings.production`, but `SECRET_KEY` is missing or still set to the default development key.
   - **Fix:** Generate a random key with `python -c "import secrets; print(secrets.token_urlsafe(50))"` and set it in `.env` or your Render Environment tab.

2. **`DisallowedHost at /` (HTTP 400 Bad Request)**
   - **Cause:** The domain name you used in the browser is not listed in `ALLOWED_HOSTS`.
   - **Fix:** Add your domain (e.g. `ALLOWED_HOSTS=billing.yourshop.com,localhost`) to `.env` and restart the server.

3. **`413 Request Entity Too Large` when uploading a multi-page bill**
   - **Cause:** Nginx's default upload limit is 1 MB.
   - **Fix:** Ensure `client_max_body_size 20M;` is inside your `server` block in `/etc/nginx/sites-available/aibilling` (already included in `deploy/nginx.conf`) and run `sudo systemctl reload nginx`.

4. **Healthcheck Verification**
   - Visit `https://your-domain.com/healthz/` at any time.
   - A healthy server returns HTTP 200: `{"status": "ok", "database": "connected"}`.
