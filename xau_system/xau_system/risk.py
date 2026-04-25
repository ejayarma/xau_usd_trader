from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .config import SystemConfig, TierCaps
from .models import Side


def floor_to_step(value: float, step: float) -> float:
    return math.floor(value / step) * step


@dataclass(slots=True)
class AccountState:
    balance: float
    equity: float
    daily_loss: float = 0.0
    weekly_loss: float = 0.0
    last_stop_hit_at: datetime | None = None
    last_stop_hit_side: Side | None = None
    last_stop_hit_lot: float | None = None


class RiskManager:
    def __init__(self, config: SystemConfig, tiers: TierCaps):
        self.config = config
        self.tiers = tiers

    def calc_lot_size(self, account_balance: float, stop_points: int, weak_trend: bool = False, marginal_rr: bool = False, tier_min_override: float | None = None) -> float:
        risk_lot = floor_to_step((account_balance * self.config.risk_pct) / (stop_points * self.config.dollars_per_raw_point_per_standard_lot), self.config.broker_step)
        tier_max = tier_min_override if tier_min_override is not None else self.tiers.max_lot_for_balance(account_balance)
        final_lot = min(risk_lot, tier_max)
        if weak_trend:
            final_lot *= self.config.weak_trend_size_factor
        if marginal_rr:
            final_lot *= self.config.marginal_rr_size_factor
        return max(floor_to_step(final_lot, self.config.broker_step), self.config.broker_step)

    def validate_stop_distance(self, stop_distance_points: int, atr_15m_points: float) -> tuple[bool, int, int]:
        effective_min = int(max(self.config.stop_abs_min, self.config.stop_atr_min_fraction * atr_15m_points))
        effective_max = int(max(self.config.stop_abs_max, self.config.stop_atr_max_fraction * atr_15m_points))
        if effective_min > effective_max:
            raise RuntimeError("Stop validation impossible: effective_min > effective_max")
        if stop_distance_points < effective_min:
            return True, effective_min, effective_max
        if stop_distance_points > effective_max:
            return False, effective_min, effective_max
        return True, effective_min, effective_max

    def is_daily_locked(self, state: AccountState) -> bool:
        return state.daily_loss >= state.balance * self.config.daily_loss_pct

    def is_weekly_locked(self, state: AccountState) -> bool:
        return state.weekly_loss >= state.balance * self.config.weekly_loss_pct

    def revenge_trade_detected(self, state: AccountState, new_entry_time: datetime, side: Side, lot_size: float) -> bool:
        if not state.last_stop_hit_at or not state.last_stop_hit_side or state.last_stop_hit_lot is None:
            return False
        return (
            new_entry_time <= state.last_stop_hit_at + timedelta(minutes=15)
            and side == state.last_stop_hit_side
            and lot_size >= state.last_stop_hit_lot
        )
