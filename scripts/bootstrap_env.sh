#!/usr/bin/env bash
set -euo pipefail

mode="${1:-preview}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
venv_dir="${VENV_DIR:-${repo_root}/.venv}"

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

if [[ ! -x "${venv_dir}/bin/python" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    bootstrap_python="python3"
  elif command -v python >/dev/null 2>&1; then
    bootstrap_python="python"
  else
    echo "Python 3 is required to run the audit preview." >&2
    exit 1
  fi
  echo "Creating isolated environment at ${venv_dir}"
  "${bootstrap_python}" -m venv "${venv_dir}"
fi

if "${venv_dir}/bin/python" -c "${probe}" >/dev/null 2>&1; then
  if [[ "${mode}" == "preview" ]] || {
    [[ -x "${venv_dir}/bin/ruff" ]] && [[ -x "${venv_dir}/bin/cfn-lint" ]]
  }; then
    exit 0
  fi
fi

echo "Installing pinned ${mode} dependencies"
PIP_DISABLE_PIP_VERSION_CHECK=1 "${venv_dir}/bin/python" -m pip install \
  --requirement "${requirements_file}"
"${venv_dir}/bin/python" -c "${probe}"
