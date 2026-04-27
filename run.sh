#!/usr/bin/env bash
# Convenience launcher. Creates a venv, installs deps, and starts Streamlit.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if [[ ! -d .venv ]]; then
  echo ">> Creating virtualenv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo ">> Installing requirements"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if [[ ! -f .env && -f .env.example ]]; then
  echo ">> No .env found. Copy .env.example -> .env and add your ANTHROPIC_API_KEY for full features."
fi

echo ">> Generating sample data (first run only)"
python -m cmbs.mock_data > /dev/null

echo ">> Launching Streamlit"
streamlit run app.py "$@"
