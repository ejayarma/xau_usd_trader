from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .alerts import AlertManager
from .broker import OandaBroker, PaperBroker
from .config import Mode, SystemConfig, TPVariant
from .engine import TradingEngine
from .journal import Journal


def load_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def build_engine(args: argparse.Namespace) -> TradingEngine:
    config = SystemConfig(mode=Mode(args.mode), tp_variant=TPVariant(args.variant))
    broker = PaperBroker() if args.broker == "paper" else OandaBroker()
    journal = Journal(args.db)
    alerts = AlertManager()
    return TradingEngine(config=config, broker=broker, journal=journal, alerts=alerts)


def cmd_scan(args: argparse.Namespace) -> None:
    engine = build_engine(args)
    m15 = load_csv(args.m15)
    h1 = load_csv(args.h1)
    d1 = load_csv(args.d1)
    signals = engine.scan(m15, h1, d1)
    if not signals:
        print("No valid signals.")
        return
    for sig in signals:
        print(sig)


def cmd_paper(args: argparse.Namespace) -> None:
    engine = build_engine(args)
    metrics = engine.paper_run(load_csv(args.m15), load_csv(args.h1), load_csv(args.d1))
    print(metrics)


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="XAU/USD Trading System v2.3")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--m15", required=True)
        sp.add_argument("--h1", required=True)
        sp.add_argument("--d1", required=True)
        sp.add_argument("--mode", choices=[m.value for m in Mode], default=Mode.SEMI_AUTO.value)
        sp.add_argument("--variant", choices=[v.value for v in TPVariant], default=TPVariant.A.value)
        sp.add_argument("--broker", choices=["paper", "oanda"], default="paper")
        sp.add_argument("--db", default="journal.sqlite3")

    scan = sub.add_parser("scan")
    add_common(scan)
    scan.set_defaults(func=cmd_scan)

    paper = sub.add_parser("paper")
    add_common(paper)
    paper.set_defaults(func=cmd_paper)
    return p


def main() -> None:
    parser = make_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
