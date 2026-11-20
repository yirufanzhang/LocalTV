#!/usr/bin/env bash
# 第一次运行会创建虚拟环境并安装依赖，之后直接启动。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

pick_python() {
  local candidate
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 \
      && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

if ! PY="$(pick_python)"; then
  echo "需要 Python 3.10 或更高。macOS 可先执行：brew install python@3.12" >&2
  exit 1
fi

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "正在创建虚拟环境…"
  "$PY" -m venv "$ROOT/.venv"
fi

VENV_PY="$ROOT/.venv/bin/python"
STAMP="$ROOT/.venv/.requirements.sha"
REQ_HASH="$("$VENV_PY" -c 'import hashlib, pathlib; print(hashlib.sha256(pathlib.Path("requirements.txt").read_bytes()).hexdigest())')"

if [[ ! -f "$STAMP" || "$(cat "$STAMP")" != "$REQ_HASH" ]]; then
  echo "正在安装依赖…"
  "$VENV_PY" -m pip install -r requirements.txt
  printf '%s\n' "$REQ_HASH" > "$STAMP"
fi

HOST="${LOCALTV_HOST:-127.0.0.1}"
PORT="${LOCALTV_PORT:-8787}"
URL="http://${HOST}:${PORT}"

if [[ "${LOCALTV_NO_OPEN:-}" != "1" && "$(uname -s)" == "Darwin" ]]; then
  (sleep 1 && open "$URL") >/dev/null 2>&1 &
fi

echo "LocalTV：${URL}"
echo "关掉这个窗口就会停止。"
exec "$VENV_PY" -m localtv
