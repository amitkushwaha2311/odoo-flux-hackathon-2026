# Brightloop Subscription Intelligence

**Brightloop** is a subscription management platform built on **Odoo 20.0 Community Edition**.

---

## Technology Stack

| Component | Version | Notes |
|---|---|---|
| Odoo | 20.0 Community | Application server |
| PostgreSQL | 16 | Database |
| Docker | Latest stable | Container runtime |
| Docker Compose | V2 | Orchestration |

---

## Prerequisites

Before starting, ensure the following are installed on your machine:

- **Docker Desktop** (Windows) — [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/)
- **Git** — [https://git-scm.com/](https://git-scm.com/)

---

## Environment Setup

### 1. Copy the environment file

```bash
cp .env.example .env
```

### 2. Edit `.env` with secure credentials

```env
POSTGRES_DB=brightloop_dev
POSTGRES_USER=brightloop
POSTGRES_PASSWORD=<your-strong-password>
ODOO_MASTER_PASSWORD=<your-strong-master-password>
```

> ⚠️ **Never commit `.env` to version control.** It is listed in `.gitignore`.

---

## Starting Docker Desktop

If Docker Desktop is not running:

1. Open **Docker Desktop** from the Start Menu or System Tray.
2. Wait for the Docker whale icon in the system tray to become steady (not animated).
3. Verify Docker is running:
   ```bash
   docker info
   ```

---

## Starting the Application

```bash
# Start all services in the background
docker compose up -d

# Follow logs (Ctrl+C to stop following, containers keep running)
docker compose logs -f

# Follow Odoo logs only
docker compose logs -f odoo
```

Once started, open your browser at:

**http://localhost:8069**

---

## Stopping the Application

```bash
# Stop containers (data is preserved in named volumes)
docker compose down

# Stop containers AND remove volumes (WARNING: destroys all data)
docker compose down -v
```

---

## Database Persistence

PostgreSQL data is stored in the named Docker volume `brightloop_db_data`.  
Odoo filestore (attachments, reports) is stored in `brightloop_odoo_data`.

Both volumes **persist across container restarts and `docker compose down`**.  
They are only destroyed with `docker compose down -v`.

To list volumes:

```bash
docker volume ls | grep brightloop
```

---

## Installing the brightloop_core Addon

1. Open Odoo at [http://localhost:8069](http://localhost:8069).
2. Create or select your database.
3. Enable **Developer Mode**: `Settings → General Settings → Developer Tools → Activate Developer Mode`.
4. Go to `Apps → Update Apps List`.
5. Search for **Brightloop Core**.
6. Click **Install**.

Alternatively, install via the command line:

```bash
docker compose exec odoo odoo -d brightloop_dev -i brightloop_core --stop-after-init
```

---

## Useful Commands

```bash
# Rebuild and restart containers
docker compose up -d --build

# Open a shell inside the Odoo container
docker compose exec odoo bash

# Open a PostgreSQL shell
docker compose exec db psql -U brightloop -d brightloop_dev

# View container status
docker compose ps

# View resource usage
docker stats

# Restart only Odoo
docker compose restart odoo
```

---

## Troubleshooting

### Odoo doesn't start

```bash
docker compose logs odoo
```

Common causes:
- `.env` file missing — run `cp .env.example .env` and set credentials.
- PostgreSQL not yet healthy — Odoo waits, but check `docker compose logs db`.
- Port 8069 already in use — check with `netstat -ano | findstr 8069` and stop the conflicting process.

### Database connection refused

```bash
docker compose exec odoo bash -c "nc -zv db 5432"
```

If this fails, the `db` container is not running or the network is misconfigured.

### Addon not discovered

Ensure the addons volume is correctly mounted:
```bash
docker compose exec odoo ls /mnt/extra-addons
```

The output should include `brightloop_core`.

### Reset everything (development only)

```bash
docker compose down -v
docker compose up -d
```

---

## Project Structure

```
odoo/
├── addons/
│   └── brightloop_core/        ← Custom Odoo addon
│       ├── __init__.py
│       ├── __manifest__.py
│       ├── models/
│       ├── security/           ← ACL, groups, record rules (Phase 2)
│       ├── data/               ← Static data fixtures
│       └── tests/              ← Automated tests
├── config/
│   └── odoo.conf               ← Odoo server configuration
├── scripts/                    ← Utility scripts
├── docker-compose.yml
├── .env.example                ← Template — copy to .env
├── .gitignore
├── requirements-dev.txt
└── README.md
```

---

## Development Phases

| Phase | Status | Description |
|---|---|---|
| Phase 1 | ✅ Completed | Foundation infrastructure & Odoo environment |
| Phase 2 | ✅ Completed | Authentication, RBAC & security architecture |
| Phase 3 | ✅ Completed | Product catalog & multi-variant management |
| Phase 4 | ✅ Completed | Multi-frequency subscription plan engine |
| Phase 5 | ✅ Completed | Quotation & sales order workflow management |
| Phase 6 | ✅ Completed | Subscription lifecycle state machine |
| Phase 7 | ✅ Completed | Tax calculation & multi-tier discount engine |
| Phase 8 | ✅ Completed | Automated recurring billing & invoice engine |
| Phase 9 | ✅ Completed | Zero-loss payment reconciliation & ledger allocations |
| Phase 10 | ✅ Completed | Customer self-service portal backend & APIs |
| Phase 11 | ✅ Completed | Financial analytics engine, MRR & cohort metrics |
| Phase 12 | ✅ Completed | Premium SaaS frontend, visual system & portal UI |

---

## Deployment & Infrastructure

### Planned Production Architecture

The planned production infrastructure for **Brightloop Subscription Intelligence** employs a multi-cloud hybrid topology engineered for global edge delivery, containerized backend processing, serverless database scaling, and durable filestore persistence:

```
[ User Browser (Desktop & Mobile) ]
                 |
                 v
       +-------------------+
       |    Vercel Edge    |  <-- Global Edge CDN, Static Assets, Edge Rewrites
       +-------------------+
                 |
                 | (Reverse Proxy /api/v1/*)
                 v
       +-------------------+
       |  Render Web Svc   |  <-- Odoo 20 Community (Docker Runtime, Ohio US East)
       +-------------------+
           |           |
           |           +-----> [ Render Persistent Disk: /var/lib/odoo (Filestore) ]
           v
       +-------------------+
       |  Neon PostgreSQL  |  <-- Serverless PostgreSQL 16 (SSL/TLS Required)
       +-------------------+
```

- **Frontend**: **Vercel**
  - Edge CDN delivery for public marketing pages, authentication views, platform dashboard console, and customer self-service portal.
  - Edge Rewrites (`vercel.json`) proxying `/api/*` requests to the Render backend, preserving first-party session cookie mechanics without cross-origin friction.
  - *Note: Deployment setup in progress; standalone frontend separation and asset bundling must be verified before production cutover.*
- **Backend**: **Odoo 20 Community on Render**
  - Fully managed containerized Web Service running Odoo 20 Community Edition.
  - Region: Ohio (US East / `us-east-ohio`).
  - Reverse proxy configuration enabled (`proxy_mode = True`).
- **Database**: **Neon PostgreSQL**
  - Serverless PostgreSQL 16 instance.
  - Compute auto-scaling and connection pooling (PgBouncer).
  - Strict TLS/SSL encryption enforced (`sslmode=require`).
- **Persistent Storage**: **Render Persistent Disk**
  - Dedicated persistent volume mounted at `/var/lib/odoo` to retain Odoo's binary filestore, generated tax receipts, customer PDF invoices, and session caches across container deployments and restarts.

---

### Current Deployment Status

| Infrastructure Component | Target Platform | Current Status | Notes |
|:---|:---|:---:|:---|
| **Neon Project** | Neon Cloud | ✅ Created | Project: `brightloop-production` |
| **PostgreSQL Branch** | Neon Cloud | ✅ Created | Production branch: `production` |
| **Render Repository** | Render | ✅ Connected | Repository: `amitkushwaha2311/odoo-flux-hackathon-2026` |
| **Render Region** | Render | ✅ Selected | Region: Ohio (US East / `us-east-ohio`) |
| **Vercel Frontend** | Vercel | ⏳ Pending | Deployment setup in progress; asset separation verification required |
| **Data & Filestore Migration** | Neon / Render | ⏳ Pending | Initial schema seeding and filestore synchronization pending |

> ⚠️ **Important**: Deployment is actively in progress. Production cutover, live DNS configuration, and traffic routing will occur after frontend separation and database migrations are fully validated.

---

### Setup Prerequisites

Before initiating production deployments, ensure the following accounts and credentials are provisioned:

1. **Neon Cloud Account**:
   - Access to project `brightloop-production` with branch `production`.
   - Connection parameters retrieved from the Neon Console (Host, Database Name, User, Password, Port `5432`, `sslmode=require`).
2. **Render Cloud Account**:
   - Authorized GitHub integration to repository `amitkushwaha2311/odoo-flux-hackathon-2026`.
   - Permissions to provision a Docker Web Service and attach a Render Persistent Disk in `Ohio (US East)`.
3. **Vercel Account**:
   - Vercel CLI or Vercel Dashboard connected to the repository or target deployment project.
4. **Environment Secret Management**:
   - All production secrets must be managed strictly via platform environment managers (Render Environment Settings, Vercel Project Variables).
   - No database credentials, connection strings, or master passwords may be committed to version control.

---

### Deployment Steps & Execution Runbook

#### Step 1: Database Provisioning (Neon PostgreSQL)
1. Verify the `brightloop-production` project and `production` branch in the Neon Console.
2. Ensure compute endpoint autoscaling limits and connection pooling are enabled.
3. Verify TLS/SSL enforcement (`sslmode=require`).

#### Step 2: Backend Web Service Deployment (Render)
1. In the Render Dashboard, create a **New +** → **Web Service**.
2. Connect repository: `amitkushwaha2311/odoo-flux-hackathon-2026` (branch: `main`).
3. Configure service parameters:
   - **Runtime**: `Docker`
   - **Region**: `Ohio (US East)`
   - **Instance Type**: Minimum Starter tier (1 CPU, 2 GB RAM).
4. Attach a **Render Persistent Disk**:
   - **Mount Path**: `/var/lib/odoo`
   - **Size**: 10 GB minimum.
5. Set production Environment Variables (via Render Dashboard):
   - `HOST=0.0.0.0`
   - `PORT=10000`
   - `DB_HOST=<neon-production-host>.neon.tech`
   - `DB_PORT=5432`
   - `DB_USER=<neon-db-user>`
   - `DB_PASSWORD=<neon-db-password>`
   - `DB_NAME=brightloop_production`
   - `DB_SSLMODE=require`
   - `ODOO_ADMIN_PASSWORD=<strong-master-password>`
6. Configure health check endpoint: `/api/v1/analytics/kpis` or `/`.

#### Step 3: Frontend Separation & Edge Deployment (Vercel)
1. Verify standalone static asset bundle (`frontend/` or static public assets).
2. Configure `vercel.json` with Edge Rewrites to route all API calls directly to the Render backend:
   ```json
   {
     "rewrites": [
       {
         "source": "/api/:path*",
         "destination": "https://<render-service-slug>.onrender.com/api/:path*"
       }
     ]
   }
   ```
3. Deploy to Vercel via Git integration or Vercel CLI:
   ```bash
   vercel --prod
   ```
4. Verify HTTP 200 responses, static asset delivery, and that API calls to `/api/v1/auth/me` proxy seamlessly to Render.

#### Step 4: Database Initialization & Module Verification
1. Run initial database schema seeding and addon installation on the Render container:
   ```bash
   odoo -d <neon-db-name> --db_host=<neon-host> --db_user=<neon-user> -i brightloop_core --stop-after-init
   ```
2. Run automated test suite against the production candidate database to confirm model integrity:
   ```bash
   odoo -d <neon-db-name> --test-enable --test-tags :brightloop_core --stop-after-init
   ```
3. Perform end-to-end user verification across customer registration, login, subscription lifecycle, and billing workflows.

---

## License

Proprietary — Brightloop © 2026. All rights reserved.

