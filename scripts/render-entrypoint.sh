#!/bin/bash
# =============================================================================
# Brightloop — Render.com Entrypoint Wrapper
# =============================================================================
#
# PROBLEM: The official Odoo entrypoint (/entrypoint.sh) reads the PORT
# environment variable as the PostgreSQL port:
#
#   : ${PORT:=${DB_PORT_5432_TCP_PORT:=5432}}
#   check_config "db_port" "$PORT"
#
# Render.com injects PORT (e.g. 10000) as the HTTP listener port, NOT the
# database port. Without this wrapper:
#   - Odoo would try to connect to Neon PostgreSQL on Render's HTTP port → FAIL
#   - Odoo would ignore Render's HTTP port and listen on hardcoded 8069 → FAIL
#
# FIX: This wrapper runs before /entrypoint.sh and:
#   1. Saves Render's HTTP PORT, then unsets it so the Odoo entrypoint does
#      not consume it as a PostgreSQL port.
#   2. Passes --http-port <RENDER_PORT> directly to Odoo on the CMD line.
#   3. Re-maps DB_HOST / DB_PORT / DB_USER / DB_PASSWORD → HOST / PORT /
#      USER / PASSWORD, which is what the Odoo entrypoint actually reads.
#   4. Sets PGSSLMODE=require for Neon PostgreSQL SSL (required by Neon).
#
# ENVIRONMENT VARIABLES (set in Render dashboard):
#   DB_HOST      — Neon PostgreSQL hostname (e.g. ep-xxx.us-east-2.aws.neon.tech)
#   DB_PORT      — PostgreSQL port (default: 5432)
#   DB_USER      — PostgreSQL username
#   DB_PASSWORD  — PostgreSQL password (use a Render secret)
#   PORT         — Injected automatically by Render as the HTTP listener port
#   ODOO_MASTER_PASSWORD — Odoo master/admin password (use a Render secret)
#
# DO NOT set HOST, PORT, USER, or PASSWORD directly — this script maps them.
# =============================================================================

set -e

# ---------------------------------------------------------------------------
# 1. Capture Render's HTTP PORT before the Odoo entrypoint consumes it
# ---------------------------------------------------------------------------
RENDER_HTTP_PORT="${PORT:-8069}"

# Unset PORT so the Odoo entrypoint does NOT treat it as the PostgreSQL port
unset PORT

# ---------------------------------------------------------------------------
# 2. Map Render-friendly DB_* env vars → what the Odoo entrypoint reads
#    The entrypoint reads: HOST, PORT, USER, PASSWORD
#    We use DB_* names to avoid the PORT collision on Render
# ---------------------------------------------------------------------------
export HOST="${DB_HOST:-${HOST:-db}}"
export PORT="${DB_PORT:-5432}"
export USER="${DB_USER:-${USER:-odoo}}"
export PASSWORD="${DB_PASSWORD:-${PASSWORD:-odoo}}"

# ---------------------------------------------------------------------------
# 3. Require SSL for Neon PostgreSQL
#    Neon mandates SSL. PGSSLMODE=require is the correct libpq setting.
#    wait-for-psql.py uses psycopg2 which respects this env var.
# ---------------------------------------------------------------------------
export PGSSLMODE="${PGSSLMODE:-require}"

# ---------------------------------------------------------------------------
# 4. Hand off to the official Odoo entrypoint, injecting the HTTP port
#    as an Odoo command-line flag AFTER the config file args.
#    The first argument to this script is always "odoo"; subsequent args
#    are passed through unchanged.
# ---------------------------------------------------------------------------
echo "[render-entrypoint] HTTP port : ${RENDER_HTTP_PORT}"
echo "[render-entrypoint] DB host   : ${HOST}"
echo "[render-entrypoint] DB port   : ${PORT}"
echo "[render-entrypoint] PGSSLMODE : ${PGSSLMODE}"

exec /entrypoint.sh "$@" "--http-port=${RENDER_HTTP_PORT}"

