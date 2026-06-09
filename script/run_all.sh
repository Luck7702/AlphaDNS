#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

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
