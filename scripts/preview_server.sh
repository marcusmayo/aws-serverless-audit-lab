#!/usr/bin/env bash
set -euo pipefail

action="${1:-start}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
venv_dir="${VENV_DIR:-${repo_root}/.venv}"
host="${PREVIEW_HOST:-0.0.0.0}"
port="${PREVIEW_PORT:-8000}"
runtime_dir="${PREVIEW_RUNTIME_DIR:-${TMPDIR:-/tmp}}"
runtime_key="$(printf '%s' "${repo_root}" | cksum | awk '{print $1}')"
pid_file="${PREVIEW_PID_FILE:-${runtime_dir}/aws-audit-preview-${runtime_key}-${port}.pid}"
log_file="${PREVIEW_LOG_FILE:-${runtime_dir}/aws-audit-preview-${runtime_key}-${port}.log}"

if [[ "${venv_dir}" != /* ]]; then
  venv_dir="${repo_root}/${venv_dir}"
fi
preview_python="${venv_dir}/bin/python"

healthcheck() {
  "${preview_python}" - "${port}" <<'PY' >/dev/null 2>&1
import json
import sys
from urllib.request import urlopen

with urlopen(f"http://127.0.0.1:{sys.argv[1]}/api/health", timeout=1) as response:
    payload = json.load(response)
    if (
        response.status != 200
        or payload.get("status") != "ok"
        or payload.get("service") != "aws-serverless-audit-lab"
    ):
        raise SystemExit(1)
PY
}

read_pid() {
  [[ -f "${pid_file}" ]] && tr -d '[:space:]' < "${pid_file}"
}

is_preview_pid() {
  local pid="$1"
  local command
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  kill -0 "${pid}" 2>/dev/null || return 1
  [[ -r "/proc/${pid}/cmdline" ]] || return 1
  command="$(tr '\0' ' ' < "/proc/${pid}/cmdline")"
  [[ "${command}" == *" -m preview.app"* ]] || return 1
  [[ "$(readlink -f "/proc/${pid}/cwd")" == "${repo_root}" ]]
}

start_preview() {
  VENV_DIR="${venv_dir}" bash "${script_dir}/bootstrap_env.sh" preview

  if healthcheck; then
    echo "Audit preview already running at http://127.0.0.1:${port}"
    return
  fi

  local stale_pid
  stale_pid="$(read_pid || true)"
  if [[ -n "${stale_pid}" ]] && is_preview_pid "${stale_pid}"; then
    echo "Replacing managed preview process ${stale_pid} because its health contract is stale."
    stop_preview
  fi
  rm -f -- "${pid_file}"

  (
    cd -- "${repo_root}"
    nohup "${preview_python}" -m preview.app --host "${host}" --port "${port}" \
      >>"${log_file}" 2>&1 </dev/null &
    printf '%s\n' "$!" > "${pid_file}"
  )

  local attempt
  for attempt in $(seq 1 40); do
    if healthcheck; then
      echo "Audit preview ready on port ${port}. Open the Codespaces forwarded URL."
      echo "Runtime log: ${log_file}"
      return
    fi
    sleep 0.25
  done

  echo "Preview did not become healthy. Recent log output:" >&2
  tail -n 30 "${log_file}" >&2 || true
  exit 1
}

stop_preview() {
  local pid
  pid="$(read_pid || true)"
  if [[ -z "${pid}" ]]; then
    echo "No managed preview process is recorded."
    return
  fi
  if ! is_preview_pid "${pid}"; then
    rm -f -- "${pid_file}"
    echo "Removed a stale preview PID file; no managed process was stopped."
    return
  fi
  kill "${pid}"
  for _ in $(seq 1 20); do
    kill -0 "${pid}" 2>/dev/null || break
    sleep 0.1
  done
  if kill -0 "${pid}" 2>/dev/null; then
    echo "Preview process ${pid} did not stop cleanly." >&2
    exit 1
  fi
  rm -f -- "${pid_file}"
  echo "Stopped audit preview process ${pid}."
}

status_preview() {
  VENV_DIR="${venv_dir}" bash "${script_dir}/bootstrap_env.sh" preview
  if healthcheck; then
    echo "Audit preview is healthy at http://127.0.0.1:${port}"
    return
  fi
  echo "Audit preview is not responding on port ${port}." >&2
  exit 1
}

case "${action}" in
  start) start_preview ;;
  stop) stop_preview ;;
  status) status_preview ;;
  *)
    echo "Usage: bash scripts/preview_server.sh [start|stop|status]" >&2
    exit 2
    ;;
esac
