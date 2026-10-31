#!/usr/bin/env bash
# =============================================================================
# scripts/start.sh — Start Brightloop containers
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Ensure .env exists
if [ ! -f .env ]; then
  echo "ERROR: .env file not found."
  echo "Run: cp .env.example .env && edit .env with real credentials."
  exit 1
fi

echo "Starting Brightloop services..."
docker compose up -d

echo ""
echo "Brightloop is starting. Follow logs with:"
echo "  docker compose logs -f"
echo ""
echo "Odoo will be available at http://localhost:8069 once the health check passes."

