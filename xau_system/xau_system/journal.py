from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import Iterable

from .models import EntrySignal, Position


SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id TEXT PRIMARY KEY,
    opened_at TEXT,
    closed_at TEXT,
    symbol TEXT,
    side TEXT,
    session TEXT,
    entry_price REAL,
    stop_price REAL,
    tp_price REAL,
    lot_size REAL,
    tp_variant TEXT,
    initial_stop_distance_points INTEGER,
    close_price REAL,
    pnl_dollars REAL,
    is_open INTEGER
);
CREATE TABLE IF NOT EXISTS signals (
    ts TEXT,
    symbol TEXT,
    side TEXT,
    session TEXT,
    entry_price REAL,
    stop_price REAL,
    tp_price REAL,
    lot_size REAL,
    rr_multiple REAL,
    spread_points INTEGER,
    tp_variant TEXT,
    reasons TEXT
);
CREATE TABLE IF NOT EXISTS breaches (
    ts TEXT,
    breach_type TEXT,
    detail TEXT
);
"""


class Journal:
    def __init__(self, db_path: str | Path = "journal.sqlite3"):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def log_signal(self, signal: EntrySignal) -> None:
        self.conn.execute(
            "INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                signal.timestamp.isoformat(),
                signal.symbol,
                signal.side.value,
                signal.session.value,
                signal.entry_price,
                signal.stop_price,
                signal.tp_price,
                signal.lot_size,
                signal.rr_multiple,
                signal.spread_points,
                signal.tp_variant.value,
                " | ".join(signal.reasons),
            ),
        )
        self.conn.commit()

    def open_trade(self, position: Position) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                position.trade_id,
                position.opened_at.isoformat(),
                None,
                position.symbol,
                position.side.value,
                position.session.value,
                position.entry_price,
                position.stop_price,
                position.tp_price,
                position.lot_size,
                position.tp_variant.value,
                position.initial_stop_distance_points,
                None,
                0.0,
                1,
            ),
        )
        self.conn.commit()

    def close_trade(self, position: Position) -> None:
        self.conn.execute(
            "UPDATE trades SET closed_at=?, close_price=?, pnl_dollars=?, is_open=0 WHERE trade_id=?",
            (position.closed_at.isoformat() if position.closed_at else None, position.close_price, position.pnl_dollars, position.trade_id),
        )
        self.conn.commit()

    def log_breach(self, ts: str, breach_type: str, detail: str) -> None:
        self.conn.execute("INSERT INTO breaches VALUES (?, ?, ?)", (ts, breach_type, detail))
        self.conn.commit()

    def metrics(self) -> dict[str, float]:
        rows = self.conn.execute("SELECT pnl_dollars FROM trades WHERE is_open=0").fetchall()
        pnls = [r[0] for r in rows]
        if not pnls:
            return {"trade_count": 0, "win_rate": 0.0, "profit_factor": 0.0, "expectancy": 0.0, "avg_winner": 0.0, "avg_loser": 0.0}
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p < 0]
        gross_profit = sum(winners)
        gross_loss = abs(sum(losers))
        return {
            "trade_count": len(pnls),
            "win_rate": len(winners) / len(pnls),
            "profit_factor": gross_profit / gross_loss if gross_loss else float("inf"),
            "expectancy": mean(pnls),
            "avg_winner": mean(winners) if winners else 0.0,
            "avg_loser": mean(losers) if losers else 0.0,
        }
