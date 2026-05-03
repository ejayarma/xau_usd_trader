****# XAU/USD Trading System (v2.3 implementation scaffold)

This project implements the **core logic** of the uploaded XAU/USD Trading System v2.3 specification:

- OANDA-point normalization
- risk and tier-cap lot sizing
- regime detection (EMA/ADX/range)
- key level detection
- session/news/spread filters
- entry validation for London/NY and Asia
- stop-loss and TP variants A/B/C
- journaling, breach logging, validation metrics
- architecture split:
  - `semi_auto`: alert-first / manual approval workflow
  - `full_auto`: deterministic execution workflow

## Important boundaries

This is a **usable engineering baseline**, not a guaranteed-profitable bot.
You still need:

1. OANDA credentials for live/practice execution
2. a calendar event source (TradingEconomics / ForexFactory adapter)
3. historical XAUUSD candle data in CSV or API form
4. paper-trading validation before live use

## Project structure

- `xau_system/config.py` - configuration and thresholds
- `xau_system/models.py` - core dataclasses/enums
- `xau_system/indicators.py` - EMA/ATR/ADX and swing logic
- `xau_system/levels.py` - level detection / staleness
- `xau_system/risk.py` - lot sizing, stop validation, limits
- `xau_system/rules.py` - market regime and entry rules
- `xau_system/journal.py` - SQLite journaling + metrics
- `xau_system/alerts.py` - Telegram / console alerts
- `xau_system/broker.py` - paper broker + OANDA broker scaffold
- `xau_system/engine.py` - orchestration engine
- `xau_system/main.py` - CLI entrypoint

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment variables

```bash
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
export OANDA_API_TOKEN="..."
export OANDA_ACCOUNT_ID="..."
export OANDA_ENV="practice"   # or live
```

## CSV input format

For backtesting / paper run, supply CSVs with columns:

- `time` (UTC ISO8601 or parseable timestamp)
- `open`
- `high`
- `low`
- `close`
- `spread_points`

Recommended files:

- 15M candles CSV
- 1H candles CSV
- 1D candles CSV

## Example: scan signals from CSV

```bash
python -m xau_system.main \
  scan \
  --m15 data/xau_m15.csv \
  --h1 data/xau_h1.csv \
  --d1 data/xau_d1.csv \
  --mode semi_auto
```

## Example: run paper trading loop from CSV

```bash
python -m xau_system.main \
  paper \
  --m15 data/xau_m15.csv \
  --h1 data/xau_h1.csv \
  --d1 data/xau_d1.csv \
  --mode semi_auto
```

## Notes

- The calendar adapter is intentionally abstract. You can plug in TradingEconomics or ForexFactory.
- Architecture A sends alerts and records approvals/rejections.
- Architecture B can place deterministic trades through OANDA once you wire credentials and confirm endpoint behavior.
- Variant A is the default, matching the spec, but the journal computes validation metrics so you can compare A/B/C.
