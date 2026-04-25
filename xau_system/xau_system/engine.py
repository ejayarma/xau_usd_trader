from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

from .alerts import AlertManager
from .broker import Broker, PaperBroker
from .config import DEFAULT_CONFIG, DEFAULT_TIERS, Mode, SystemConfig, TPVariant
from .indicators import add_common_indicators, ensure_time_index, raw_points_from_price_move
from .journal import Journal
from .levels import LevelDetector
from .models import CalendarEvent, EntrySignal, Position, Side
from .risk import AccountState, RiskManager
from .rules import RuleContext, RuleEngine


@dataclass(slots=True)
class TradingEngine:
    config: SystemConfig = field(default_factory=lambda: DEFAULT_CONFIG)
    journal: Journal = field(default_factory=Journal)
    alerts: AlertManager = field(default_factory=AlertManager)
    broker: Broker = field(default_factory=PaperBroker)

    def __post_init__(self) -> None:
        self.risk = RiskManager(self.config, DEFAULT_TIERS)
        self.rule_engine = RuleEngine(self.config, self.risk)
        self.level_detector = LevelDetector(self.config)
        self.account = AccountState(balance=1000.0, equity=1000.0)
        self.positions: dict[str, Position] = {}
        self.freeze_until: datetime | None = None

    def prepare_frames(self, m15: pd.DataFrame, h1: pd.DataFrame, d1: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        return add_common_indicators(m15), add_common_indicators(h1), add_common_indicators(d1)

    def scan(self, m15: pd.DataFrame, h1: pd.DataFrame, d1: pd.DataFrame, events: list[CalendarEvent] | None = None) -> list[EntrySignal]:
        events = events or []
        m15, h1, d1 = self.prepare_frames(m15, h1, d1)
        levels = self.level_detector.detect(m15, h1).levels
        now = m15.index[-1].to_pydatetime()
        if self.freeze_until and now < self.freeze_until:
            return []
        regime = self.rule_engine.market_regime(h1, d1, m15)
        if regime.volatility_shock:
            self.freeze_until = now + timedelta(minutes=self.config.volatility_freeze_minutes)
            self.alerts.send(f"VOLATILITY_SHOCK_DETECTED at {now.isoformat()} — new entries frozen until {self.freeze_until.isoformat()}")
            return []
        spread_points = int(m15["spread_points"].iloc[-1]) if "spread_points" in m15.columns else 500
        ctx = RuleContext(m15=m15, h1=h1, d1=d1, spread_points=spread_points, now=now, levels=levels, account=self.account, events=events)
        signals: list[EntrySignal] = []
        for side in (Side.LONG, Side.SHORT):
            try:
                sig = self.rule_engine.build_signal(ctx, side, self.config.tp_variant)
            except Exception as exc:
                self.alerts.send(f"Rule evaluation error: {exc}")
                sig = None
            if sig:
                signals.append(sig)
                self.journal.log_signal(sig)
        return signals

    def handle_signal(self, signal: EntrySignal, auto_approve: bool = False) -> Position | None:
        self.alerts.send_signal(signal)
        if signal.requires_manual_confirmation and not auto_approve and self.config.mode == Mode.SEMI_AUTO:
            return None
        result = self.broker.submit_bracket_order(signal)
        if not result.accepted:
            self.alerts.send(f"Order rejected: {result.message}")
            return None
        trade_id = result.order_id or str(uuid.uuid4())
        position = Position(
            trade_id=trade_id,
            opened_at=signal.timestamp,
            symbol=signal.symbol,
            side=signal.side,
            entry_price=result.fill_price or signal.entry_price,
            stop_price=signal.stop_price,
            lot_size=signal.lot_size,
            tp_price=signal.tp_price,
            tp_variant=signal.tp_variant,
            initial_stop_distance_points=signal.stop_distance_points,
            session=signal.session,
        )
        self.positions[position.trade_id] = position
        self.journal.open_trade(position)
        return position

    def update_positions(self, latest_price: float, now: datetime, m15: pd.DataFrame) -> None:
        atr_points = raw_points_from_price_move(float(m15["atr_14"].iloc[-1]))
        adx15 = float(m15["adx_14"].iloc[-1]) if "adx_14" in m15.columns else 0.0
        for trade_id, position in list(self.positions.items()):
            if not position.is_open:
                continue
            hit_stop = latest_price <= position.stop_price if position.side == Side.LONG else latest_price >= position.stop_price
            hit_tp = latest_price >= position.tp_price if position.side == Side.LONG else latest_price <= position.tp_price
            should_force_close = False
            if position.session.value == "asia" and (now.hour > self.config.asia_hard_exit_hour_utc or (now.hour == self.config.asia_hard_exit_hour_utc and now.minute >= self.config.asia_hard_exit_minute_utc)):
                should_force_close = True
            if now.hour >= self.config.london_end_utc:
                should_force_close = True

            if position.tp_variant == TPVariant.A and not position.partial_closed:
                target_reached = (latest_price - position.entry_price) >= position.initial_stop_distance_points * 0.01 if position.side == Side.LONG else (position.entry_price - latest_price) >= position.initial_stop_distance_points * 0.01
                if target_reached:
                    position.stop_price = position.entry_price
                trail_distance = max(self.config.trail_min_points, int(self.config.trail_atr_fraction * atr_points)) * 0.01
                if position.side == Side.LONG:
                    new_stop = latest_price - trail_distance
                    if new_stop > position.stop_price:
                        position.stop_price = round(new_stop, 2)
                else:
                    new_stop = latest_price + trail_distance
                    if new_stop < position.stop_price:
                        position.stop_price = round(new_stop, 2)
                if adx15 < self.config.resistance_momentum_adx_cutoff and abs(latest_price - position.tp_price) <= self.config.resistance_alert_distance_points * 0.01 and self.config.mode == Mode.FULL_AUTO:
                    should_force_close = True

            if hit_stop or hit_tp or should_force_close:
                close_res = self.broker.close_position(position, latest_price)
                if close_res.accepted:
                    position.is_open = False
                    position.close_price = latest_price
                    position.closed_at = now
                    pnl_points = raw_points_from_price_move((latest_price - position.entry_price) if position.side == Side.LONG else (position.entry_price - latest_price))
                    position.pnl_dollars = pnl_points * self.config.dollars_per_raw_point_per_standard_lot * position.lot_size
                    self.account.balance += position.pnl_dollars
                    self.account.equity = self.account.balance
                    if position.pnl_dollars < 0:
                        self.account.daily_loss += abs(position.pnl_dollars)
                        self.account.weekly_loss += abs(position.pnl_dollars)
                        self.account.last_stop_hit_at = now
                        self.account.last_stop_hit_side = position.side
                        self.account.last_stop_hit_lot = position.lot_size
                    self.journal.close_trade(position)
                    del self.positions[trade_id]

    def paper_run(self, m15: pd.DataFrame, h1: pd.DataFrame, d1: pd.DataFrame) -> dict[str, float]:
        m15 = ensure_time_index(m15)
        h1 = ensure_time_index(h1)
        d1 = ensure_time_index(d1)
        for ts in m15.index[100:]:
            m15_slice = m15.loc[:ts].copy()
            h1_slice = h1.loc[:ts].copy()
            d1_slice = d1.loc[:ts].copy()
            if len(h1_slice) < 60 or len(d1_slice) < 20:
                continue
            signals = self.scan(m15_slice, h1_slice, d1_slice, events=[])
            for sig in signals:
                self.handle_signal(sig, auto_approve=True)
            self.update_positions(float(m15_slice["close"].iloc[-1]), ts.to_pydatetime(), add_common_indicators(m15_slice))
        return self.journal.metrics()
