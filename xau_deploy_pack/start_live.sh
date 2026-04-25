#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

mkdir -p data runtime runtime/logs

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Practice/live realtime mode should point to your actual live loop entrypoint once added.
# This package ships the safe CSV/paper command as a default example.
python -m xau_system.main \
  paper \
  --m15 "${CSV_M15_PATH:-./data/xau_m15.csv}" \
  --h1 "${CSV_H1_PATH:-./data/xau_h1.csv}" \
  --d1 "${CSV_D1_PATH:-./data/xau_d1.csv}" \
  --mode "${BOT_MODE:-semi_auto}" \
  --variant "${TP_VARIANT:-A}" \
  --broker "${BROKER_MODE:-paper}" \
  --db ./data/journal.sqlite3
