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
| Phase 1 | ✅ In Progress | Foundation infrastructure |
| Phase 2 | ⏳ Pending | Authentication & security |
| Phase 3 | ⏳ Pending | Subscription data models |
| Phase 4 | ⏳ Pending | Billing & invoicing |
| Phase 5 | ⏳ Pending | Reporting & analytics |

---

## License

Proprietary — Brightloop © 2026. All rights reserved.

