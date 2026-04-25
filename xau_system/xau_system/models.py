from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from .config import TPVariant


class TrendDirection(str, Enum):
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    RANGE = "range"


class TrendStrength(str, Enum):
    STRONG = "strong"
    WEAK = "weak"
    NONE = "none"


class SessionType(str, Enum):
    LONDON_NY = "london_ny"
    ASIA = "asia"
    DEAD_ZONE = "dead_zone"
    CLOSED = "closed"


class LevelTier(str, Enum):
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


class CandleType(str, Enum):
    HAMMER = "hammer"
    SHOOTING_STAR = "shooting_star"
    BULLISH_ENGULFING = "bullish_engulfing"
    BEARISH_ENGULFING = "bearish_engulfing"
    DOJI_BULL = "doji_bull"
    DOJI_BEAR = "doji_bear"
    NONE = "none"


@dataclass(slots=True)
class MarketRegime:
    direction: TrendDirection
    strength: TrendStrength
    adx: float
    atr_1d_points: float
    volatility_shock: bool
    range_high: Optional[float] = None
    range_low: Optional[float] = None
    range_size_points: Optional[float] = None


@dataclass(slots=True)
class Level:
    price: float
    tier: LevelTier
    label: str
    source: str
    reaction_points: float
    retest_count: int
    session_only: Optional[str] = None
    created_at: Optional[datetime] = None
    last_test_at: Optional[datetime] = None
    valid: bool = True


@dataclass(slots=True)
class EntrySignal:
    timestamp: datetime
    symbol: str
    side: Side
    session: SessionType
    regime: MarketRegime
    level: Level
    candle_type: CandleType
    entry_price: float
    stop_price: float
    stop_distance_points: int
    lot_size: float
    tp_price: float
    rr_multiple: float
    spread_points: int
    tp_variant: TPVariant
    reasons: list[str] = field(default_factory=list)
    requires_manual_confirmation: bool = False


@dataclass(slots=True)
class Position:
    trade_id: str
    opened_at: datetime
    symbol: str
    side: Side
    entry_price: float
    stop_price: float
    lot_size: float
    tp_price: float
    tp_variant: TPVariant
    initial_stop_distance_points: int
    session: SessionType
    partial_closed: bool = False
    is_open: bool = True
    trailing_stop: Optional[float] = None
    close_price: Optional[float] = None
    closed_at: Optional[datetime] = None
    pnl_dollars: float = 0.0


@dataclass(slots=True)
class CalendarEvent:
    name: str
    tier: int
    start_time: datetime
    end_time: datetime


@dataclass(slots=True)
class BrokerOrderResult:
    accepted: bool
    order_id: Optional[str] = None
    fill_price: Optional[float] = None
    message: str = ""
