#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Python was not found in PATH."
  exit 1
fi

echo "Using Python: ${PYTHON_BIN}"

if [ ! -d "${VENV_DIR}" ]; then
  echo "Creating virtual environment at ${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip setuptools wheel

if [ -f "${ROOT_DIR}/requirements-dev.txt" ]; then
  python -m pip install -r "${ROOT_DIR}/requirements-dev.txt"
fi

python -m pip install -e "${ROOT_DIR}"

echo "Installation finished."
echo "Run: source .venv/bin/activate && tools --help"
