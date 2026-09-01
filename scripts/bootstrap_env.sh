#!/usr/bin/env bash
set -euo pipefail

mode="${1:-preview}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
venv_dir="${VENV_DIR:-${repo_root}/.venv}"
bootstrap_python=""

if [[ "${venv_dir}" != /* ]]; then
  venv_dir="${repo_root}/${venv_dir}"
fi

case "${mode}" in
  preview)
    requirements_file="${repo_root}/requirements.txt"
    probe="import yaml"
    ;;
  dev)
    requirements_file="${repo_root}/requirements-dev.txt"
    probe="import boto3, cfnlint, pytest, yaml"
    ;;
  *)
    echo "Usage: bash scripts/bootstrap_env.sh [preview|dev]" >&2
    exit 2
    ;;
esac

select_bootstrap_python() {
  local candidate
  local resolved
  local -a candidates=()

  if [[ -n "${BOOTSTRAP_PYTHON:-}" ]]; then
    candidates+=("${BOOTSTRAP_PYTHON}")
  fi
  candidates+=(python3 python)

  for candidate in "${candidates[@]}"; do
    command -v "${candidate}" >/dev/null 2>&1 || continue
    resolved="$("${candidate}" -c \
      'import os, sys; print(os.path.realpath(getattr(sys, "_base_executable", sys.executable)))' \
      2>/dev/null || true)"
    if [[ -n "${resolved}" ]] && [[ -x "${resolved}" ]]; then
      bootstrap_python="${resolved}"
      return
    fi
  done

  echo "Python 3 with venv support is required to run the audit preview." >&2
  exit 1
}

create_venv() {
  select_bootstrap_python
  echo "Creating isolated environment at ${venv_dir}"
  "${bootstrap_python}" -m venv "${venv_dir}"
}

rebuild_venv() {
  select_bootstrap_python
  echo "Rebuilding incomplete isolated environment at ${venv_dir}"
  "${bootstrap_python}" -m venv --clear "${venv_dir}"
}

venv_python="${venv_dir}/bin/python"
if [[ ! -x "${venv_python}" ]]; then
  create_venv
elif ! "${venv_python}" -c "import sys" >/dev/null 2>&1; then
  rebuild_venv
elif ! "${venv_python}" -m pip --version >/dev/null 2>&1; then
  echo "Repairing pip in incomplete isolated environment at ${venv_dir}"
  if ! "${venv_python}" -m ensurepip --upgrade >/dev/null 2>&1; then
    rebuild_venv
  fi
fi

if ! "${venv_python}" -m pip --version >/dev/null 2>&1; then
  echo "The isolated environment could not be repaired with pip support: ${venv_dir}" >&2
  exit 1
fi

if "${venv_python}" -c "${probe}" >/dev/null 2>&1; then
  if [[ "${mode}" == "preview" ]] || {
    [[ -x "${venv_dir}/bin/ruff" ]] && [[ -x "${venv_dir}/bin/cfn-lint" ]]
  }; then
    exit 0
  fi
fi

echo "Installing pinned ${mode} dependencies"
PIP_DISABLE_PIP_VERSION_CHECK=1 "${venv_python}" -m pip install \
  --requirement "${requirements_file}"
"${venv_python}" -c "${probe}"
