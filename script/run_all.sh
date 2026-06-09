#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

# Use a local virtualenv so pip targets it, not the system Python
# (Debian/Ubuntu mark the system Python externally-managed -- PEP 668).
if [ ! -d .venv ]; then
  echo "[*] Creating .venv ..."
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate

echo "[1/4] Installing dependencies..."
pip install -r requirements.txt

echo "[2/4] Collecting telemetry (this takes a while)..."
python3 telemetry/scanner.py --probes 3

echo "[3/4] Training model..."
python3 ml/trainer.py

echo "[4/4] Evaluating..."
python3 analysis/evaluate.py

echo ""
echo "Done. Results are in the results/ folder."
