from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Tuple


class Mode(str, Enum):
    SEMI_AUTO = "semi_auto"
    FULL_AUTO = "full_auto"


class TPVariant(str, Enum):
    A = "A"
    B = "B"
    C = "C"


@dataclass(slots=True)
class TierCaps:
    caps: Tuple[Tuple[float, float, float], ...] = (
        (500, 999.99, 0.01),
        (1000, 1999.99, 0.02),
        (2000, 4999.99, 0.05),
        (5000, 9999.99, 0.10),
        (10000, float("inf"), 0.20),
    )

    def max_lot_for_balance(self, balance: float) -> float:
        for low, high, cap in self.caps:
            if low <= balance <= high:
                return cap
        return 0.01


@dataclass(slots=True)
class SystemConfig:
    symbol: str = "XAU_USD"
    mode: Mode = Mode.SEMI_AUTO
    tp_variant: TPVariant = TPVariant.A

    point_size: float = 0.01
    dollars_per_raw_point_per_standard_lot: float = 0.10
    broker_step: float = 0.01

    risk_pct: float = 0.01
    daily_loss_pct: float = 0.02
    weekly_loss_pct: float = 0.06
    weak_trend_size_factor: float = 0.5
    marginal_rr_size_factor: float = 0.5

    london_start_utc: int = 6
    london_end_utc: int = 17
    asia_start_utc: int = 22
    asia_end_utc: int = 6
    friday_cutoff_hour_utc: int = 15
    friday_alert_hour_utc: int = 14
    friday_alert_minute_utc: int = 45
    asia_hard_exit_hour_utc: int = 5
    asia_hard_exit_minute_utc: int = 45

    adx_strong: float = 25.0
    adx_trend_cutoff: float = 20.0
    range_multiplier_h1: float = 2.0
    range_entry_atr_fraction_h1: float = 0.3

    tier1_reaction_points: int = 150
    tier2_reaction_points: int = 80
    entry_zone_min_points: int = 30
    entry_zone_atr_fraction_m15: float = 0.25
    level_invalid_close_fraction_h1: float = 0.5
    level_stale_sessions: int = 10

    spread_clean_max: int = 900
    spread_entry_block: int = 1000
    spread_warning: int = 1200
    spread_hard_alert: int = 1500
    spread_alert_consecutive_5m: int = 3

    stop_buffer_min: int = 150
    stop_buffer_atr_fraction: float = 0.3
    stop_abs_min: int = 300
    stop_abs_max: int = 800
    stop_atr_min_fraction: float = 0.5
    stop_atr_max_fraction: float = 1.5

    doji_body_fraction: float = 0.1
    doji_min_range_atr_fraction: float = 0.3
    doji_confirm_distance_atr_fraction: float = 0.5
    hammer_wick_body_ratio: float = 1.5
    close_top_fraction: float = 0.35
    close_bottom_fraction: float = 0.35

    min_rr: float = 1.5
    max_rr_variant_a: float = 3.0
    fixed_rr_variant_b: float = 2.0
    be_trigger_r: float = 1.0
    trail_min_points: int = 350
    trail_atr_fraction: float = 0.5
    resistance_alert_distance_points: int = 200
    resistance_momentum_adx_cutoff: float = 20.0

    asia_spread_max: int = 900
    asia_min_rr: float = 2.0
    volatility_shock_multiplier_m15: float = 2.0
    volatility_freeze_minutes: int = 45

    round_number_step_price: float = 100.0
    prior_test_minimum: int = 1

    gate_thresholds: Dict[str, float] = field(
        default_factory=lambda: {
            "gate2_profit_factor": 1.3,
            "gate2_win_rate": 0.50,
            "gate2_max_drawdown": 0.15,
            "gate3_profit_factor": 1.5,
        }
    )


DEFAULT_CONFIG = SystemConfig()
DEFAULT_TIERS = TierCaps()
