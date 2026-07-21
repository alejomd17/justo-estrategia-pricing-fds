#!/usr/bin/env bash
# Levanta el dashboard completo con un solo comando:
#
#   ./run_dashboard.sh
#
# - Backend FastAPI (uvicorn) en http://localhost:8000 - abre el navegador
#   una vez para el login SSO de Snowflake.
# - Frontend React (vite) en http://localhost:3000.
# Ctrl+C tumba los dos.
#
# ¿Por que no Docker? La conexion a Snowflake es SSO por navegador
# (externalbrowser) y no puede completarse dentro de un contenedor sin
# navegador; la alternativa (key-pair) sigue bloqueada por permisos. Si ese
# permiso llega algun dia, ahi si tiene sentido dockerizar.

set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d frontend/node_modules ]; then
  echo "Instalando dependencias del frontend (primera vez)..."
  (cd frontend && npm install)
fi

echo "Levantando backend en :8000 (completa el login SSO si se abre el navegador)..."
uv run uvicorn backend.api.main:app --reload --port 8000 &
BACK_PID=$!
trap 'kill "$BACK_PID" 2>/dev/null' EXIT

echo "Levantando frontend en :3000..."
cd frontend && npm run dev
