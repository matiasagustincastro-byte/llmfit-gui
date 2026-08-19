#!/usr/bin/env sh
# ---------------------------------------------------------------
#  LLM Fit GUI - lanzador para Linux y macOS (x64 y ARM)
#
#  Camino preferido: uv, que resuelve Python y el wheel de llmfit
#  de la plataforma sin instalar nada en el sistema.
#  Sin uv, cae a python3 + el llmfit que ya tengas instalado.
# ---------------------------------------------------------------
set -eu

cd "$(dirname "$0")"
PORT="${PORT:-8080}"

if command -v uv >/dev/null 2>&1; then
  echo "[ok] usando uv (resuelve Python + llmfit automaticamente)"
  exec uv run server.py --port "$PORT" "$@"
fi

# --- sin uv: hace falta python3 ---------------------------------
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done

if [ -z "$PY" ]; then
  cat <<'MSG'
[!!] No se encontro Python 3.

  Lo mas simple es instalar uv, que se encarga de todo:
      curl -LsSf https://astral.sh/uv/install.sh | sh

  O instalar Python desde el gestor de paquetes de tu distro.
MSG
  exit 1
fi

if ! command -v llmfit >/dev/null 2>&1; then
  cat <<'MSG'
[!!] Falta el binario `llmfit`. Opciones:

      uv tool install -U llmfit      (recomendado)
      pipx install llmfit
      pip install --user llmfit
      brew install llmfit           (macOS / Linuxbrew)
MSG
  exit 1
fi

exec "$PY" server.py --port "$PORT" "$@"
