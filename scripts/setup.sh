#!/usr/bin/env bash
#
# First-run setup for crux on a fresh machine.
#
#   ./scripts/setup.sh
#
# Idempotent: safe to re-run. Does everything automatable —
#   1. creates a Python venv (.venv)
#   2. installs requirements
#   3. checks the claude CLI is installed and authenticated
#   4. runs database migrations (alembic upgrade head)
#
# It does NOT edit .env — copy .env.example to .env and fill in the secrets
# yourself first (see the printed instructions / docs/quickstart.md).
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="${PYTHON:-python3}"

echo "==> crux setup ($ROOT)"

# --- 1. venv -----------------------------------------------------------------
if [ ! -d .venv ]; then
  echo "==> creating venv (.venv)"
  "$PY" -m venv .venv
else
  echo "==> venv already exists, reusing"
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# --- 2. dependencies ---------------------------------------------------------
echo "==> installing dependencies"
python -m pip install --upgrade pip >/dev/null
pip install -r requirements.txt

# --- 3. claude CLI -----------------------------------------------------------
# The app calls Claude through the `claude` CLI (Claude Code) so usage bills
# against your subscription instead of an ANTHROPIC_API_KEY.
if ! command -v claude >/dev/null 2>&1; then
  echo "!!  WARNING: \`claude\` CLI not found on PATH."
  echo "    Install Claude Code, then run \`claude\` once to log in."
  echo "    See https://docs.claude.com/claude-code"
else
  echo "==> claude CLI found: $(command -v claude)"
  echo "    (make sure you've run \`claude\` once to authenticate)"
fi

# --- 4. .env check -----------------------------------------------------------
if [ ! -f .env ]; then
  echo "!!  No .env found. Create it before migrating or running:"
  echo "      cp .env.example .env"
  echo "    Then set DATABASE_URL and AUTH_SECRET (>=16 chars)."
  echo "    Generate a secret: python3 -c \"import secrets; print(secrets.token_hex(32))\""
  echo "==> setup stopped early: .env required for migrations."
  exit 1
fi

# Load .env so DATABASE_URL is available for alembic and this shell.
set -a
# shellcheck disable=SC1091
source .env
set +a

if [ -z "${DATABASE_URL:-}" ]; then
  echo "!!  DATABASE_URL is not set in .env — fill it in, then re-run."
  exit 1
fi

# --- 5. migrate --------------------------------------------------------------
echo "==> running migrations (alembic upgrade head)"
alembic upgrade head

echo ""
echo "==> done. To start the server:"
echo "      source .venv/bin/activate"
echo "      make dev"
echo "    (.env is loaded automatically.) Open http://localhost:8000"
echo "    Login password = AUTH_SECRET"
