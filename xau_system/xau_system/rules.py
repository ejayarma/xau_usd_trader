from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

import pandas as pd

from .config import Mode, SystemConfig, TPVariant
from .indicators import raw_points_from_price_move, swing_highs, swing_lows
from .models import CandleType, CalendarEvent, EntrySignal, Level, LevelTier, MarketRegime, SessionType, Side, TrendDirection, TrendStrength
from .risk import AccountState, RiskManager


@dataclass(slots=True)
class RuleContext:
    m15: pd.DataFrame
    h1: pd.DataFrame
    d1: pd.DataFrame
    spread_points: int
    now: datetime
    levels: Sequence[Level]
    account: AccountState
    events: Sequence[CalendarEvent]


class RuleEngine:
    def __init__(self, config: SystemConfig, risk: RiskManager):
        self.config = config
        self.risk = risk

    def classify_session(self, now: datetime) -> SessionType:
        hour = now.hour
        if self.config.london_start_utc <= hour < self.config.london_end_utc:
            return SessionType.LONDON_NY
        if hour >= self.config.asia_start_utc or hour < self.config.asia_end_utc:
            return SessionType.ASIA
        if 17 <= hour < 22:
            return SessionType.DEAD_ZONE
        return SessionType.CLOSED

    def blocks_from_calendar(self, now: datetime, events: Sequence[CalendarEvent]) -> dict[str, bool]:
        tier1 = False
        tier2 = False
        tier3 = False
        for e in events:
            if e.start_time <= now <= e.end_time:
                if e.tier == 1:
                    tier1 = True
                elif e.tier == 2:
                    tier2 = True
                elif e.tier == 3:
                    tier3 = True
        return {"tier1": tier1, "tier2": tier2, "tier3": tier3}

    def market_regime(self, h1: pd.DataFrame, d1: pd.DataFrame, m15: pd.DataFrame) -> MarketRegime:
        close = float(h1["close"].iloc[-1])
        ema20 = float(h1["ema_20"].iloc[-1])
        ema50 = float(h1["ema_50"].iloc[-1])
        adx_val = float(h1["adx_14"].iloc[-1])
        atr1d_points = raw_points_from_price_move(float(d1["atr_14"].iloc[-1]))
        atr15 = float(m15["atr_14"].iloc[-1])
        latest_range_points = raw_points_from_price_move(float(m15["high"].iloc[-1] - m15["low"].iloc[-1]))
        volatility_shock = latest_range_points > self.config.volatility_shock_multiplier_m15 * raw_points_from_price_move(atr15)

        sh = swing_highs(h1, 2, 2)
        sl = swing_lows(h1, 2, 2)
        swing_high_values = h1.loc[sh, "high"].tail(3).tolist()
        swing_low_values = h1.loc[sl, "low"].tail(3).tolist()
        higher_highs = len(swing_high_values) >= 3 and swing_high_values[-1] > swing_high_values[-2] > swing_high_values[-3]
        higher_lows = len(swing_low_values) >= 3 and swing_low_values[-1] > swing_low_values[-2] > swing_low_values[-3]
        lower_highs = len(swing_high_values) >= 3 and swing_high_values[-1] < swing_high_values[-2] < swing_high_values[-3]
        lower_lows = len(swing_low_values) >= 3 and swing_low_values[-1] < swing_low_values[-2] < swing_low_values[-3]

        if close > ema20 and close > ema50 and ema20 > ema50 and higher_highs and higher_lows:
            direction = TrendDirection.UPTREND
        elif close < ema20 and close < ema50 and ema20 < ema50 and lower_highs and lower_lows:
            direction = TrendDirection.DOWNTREND
        else:
            direction = TrendDirection.RANGE

        if adx_val > self.config.adx_strong:
            strength = TrendStrength.STRONG
        elif adx_val >= self.config.adx_trend_cutoff:
            strength = TrendStrength.WEAK
        else:
            strength = TrendStrength.NONE

        range_high = float(h1["high"].tail(20).max())
        range_low = float(h1["low"].tail(20).min())
        range_size_points = raw_points_from_price_move(range_high - range_low)
        atr_h1_points = raw_points_from_price_move(float(h1["atr_14"].iloc[-1]))
        if adx_val < self.config.adx_trend_cutoff and range_size_points < self.config.range_multiplier_h1 * atr_h1_points:
            direction = TrendDirection.RANGE
            strength = TrendStrength.NONE
        return MarketRegime(direction=direction, strength=strength, adx=adx_val, atr_1d_points=atr1d_points, volatility_shock=volatility_shock, range_high=range_high, range_low=range_low, range_size_points=range_size_points)

    def find_candidate_level(self, current_price: float, levels: Sequence[Level], side: Side, atr_15m_points: int, session: SessionType) -> Level | None:
        zone_points = max(self.config.entry_zone_min_points, int(self.config.entry_zone_atr_fraction_m15 * atr_15m_points))
        best: Level | None = None
        best_distance = 10**9
        for level in levels:
            if not level.valid:
                continue
            if session != SessionType.LONDON_NY and level.tier == LevelTier.TIER_2:
                continue
            if session == SessionType.ASIA and level.tier != LevelTier.TIER_1:
                continue
            if side == Side.LONG and level.label.endswith("HIGH"):
                continue
            if side == Side.SHORT and level.label.endswith("LOW"):
                continue
            distance = raw_points_from_price_move(abs(current_price - level.price))
            if distance <= zone_points and distance < best_distance and level.retest_count >= self.config.prior_test_minimum:
                best = level
                best_distance = distance
        return best

    def candle_confirmation(self, m15: pd.DataFrame, side: Side, level_price: float, spread_points: int) -> CandleType:
        candle = m15.iloc[-1]
        prev = m15.iloc[-2]
        body = abs(float(candle.close - candle.open))
        rng = max(float(candle.high - candle.low), 1e-9)
        lower_wick = float(min(candle.open, candle.close) - candle.low)
        upper_wick = float(candle.high - max(candle.open, candle.close))
        touched = candle.low <= level_price <= candle.high
        atr_15m = float(m15["atr_14"].iloc[-1])

        if side == Side.LONG:
            if lower_wick >= self.config.hammer_wick_body_ratio * body and ((candle.close - candle.low) / rng) >= (1 - self.config.close_top_fraction) and touched:
                return CandleType.HAMMER
            if candle.close > prev.high and min(candle.open, candle.close) <= max(prev.open, prev.close) and max(candle.open, candle.close) >= min(prev.open, prev.close) and touched:
                return CandleType.BULLISH_ENGULFING
            if body < self.config.doji_body_fraction * rng and rng >= self.config.doji_min_range_atr_fraction * atr_15m and touched:
                confirm = m15.iloc[-1]
                if confirm.close > candle.high and abs(confirm.close - candle.high) <= self.config.doji_confirm_distance_atr_fraction * atr_15m and spread_points < self.config.spread_entry_block:
                    return CandleType.DOJI_BULL
        else:
            if upper_wick >= self.config.hammer_wick_body_ratio * body and ((candle.high - candle.close) / rng) >= (1 - self.config.close_bottom_fraction) and touched:
                return CandleType.SHOOTING_STAR
            if candle.close < prev.low and min(candle.open, candle.close) <= max(prev.open, prev.close) and max(candle.open, candle.close) >= min(prev.open, prev.close) and touched:
                return CandleType.BEARISH_ENGULFING
            if body < self.config.doji_body_fraction * rng and rng >= self.config.doji_min_range_atr_fraction * atr_15m and touched:
                confirm = m15.iloc[-1]
                if confirm.close < candle.low and abs(confirm.close - candle.low) <= self.config.doji_confirm_distance_atr_fraction * atr_15m and spread_points < self.config.spread_entry_block:
                    return CandleType.DOJI_BEAR
        return CandleType.NONE

    def next_target_level(self, entry_price: float, levels: Sequence[Level], side: Side, session: SessionType, variant: TPVariant) -> Level | None:
        candidates = []
        for level in levels:
            if not level.valid:
                continue
            if side == Side.LONG and level.price > entry_price:
                if variant == TPVariant.C and level.tier != LevelTier.TIER_1:
                    continue
                candidates.append(level)
            if side == Side.SHORT and level.price < entry_price:
                if variant == TPVariant.C and level.tier != LevelTier.TIER_1:
                    continue
                candidates.append(level)
        if not candidates:
            return None
        return min(candidates, key=lambda lv: abs(lv.price - entry_price))

    def build_signal(self, ctx: RuleContext, side: Side, tp_variant: TPVariant) -> EntrySignal | None:
        session = self.classify_session(ctx.now)
        if session == SessionType.DEAD_ZONE:
            return None
        if ctx.now.weekday() == 4 and ctx.now.hour >= self.config.friday_cutoff_hour_utc:
            return None
        if self.risk.is_daily_locked(ctx.account) or self.risk.is_weekly_locked(ctx.account):
            return None

        blocks = self.blocks_from_calendar(ctx.now, ctx.events)
        if session == SessionType.LONDON_NY and (blocks["tier1"] or blocks["tier2"]):
            return None

        regime = self.market_regime(ctx.h1, ctx.d1, ctx.m15)
        if regime.volatility_shock:
            return None

        current_price = float(ctx.m15["close"].iloc[-1])
        atr15_points = raw_points_from_price_move(float(ctx.m15["atr_14"].iloc[-1]))

        if session == SessionType.ASIA:
            if side != Side.LONG:
                return None
            if ctx.spread_points >= self.config.asia_spread_max:
                return None
        else:
            if ctx.spread_points >= self.config.spread_entry_block:
                return None

        if regime.direction == TrendDirection.RANGE:
            if session != SessionType.LONDON_NY:
                return None
            if side == Side.LONG and current_price > (regime.range_low or current_price) + self.config.range_entry_atr_fraction_h1 * float(ctx.h1["atr_14"].iloc[-1]):
                return None
            if side == Side.SHORT and current_price < (regime.range_high or current_price) - self.config.range_entry_atr_fraction_h1 * float(ctx.h1["atr_14"].iloc[-1]):
                return None
        else:
            if side == Side.LONG and regime.direction != TrendDirection.UPTREND:
                return None
            if side == Side.SHORT and regime.direction != TrendDirection.DOWNTREND:
                return None
            if regime.adx < self.config.adx_trend_cutoff:
                return None

        level = self.find_candidate_level(current_price, ctx.levels, side, atr15_points, session)
        if not level:
            return None

        candle = self.candle_confirmation(ctx.m15, side, level.price, ctx.spread_points)
        if candle == CandleType.NONE:
            return None

        stop_price, stop_distance_points = self._calc_stop(ctx, side, level.price)
        valid, effective_min, effective_max = self.risk.validate_stop_distance(stop_distance_points, atr15_points)
        if not valid:
            return None
        if stop_distance_points < effective_min:
            stop_distance_points = effective_min
            stop_price = current_price - stop_distance_points * 0.01 if side == Side.LONG else current_price + stop_distance_points * 0.01

        tp_price, rr_multiple = self._calc_tp(current_price, stop_distance_points, ctx.levels, side, tp_variant, session)
        if tp_price is None:
            return None
        if session == SessionType.ASIA and rr_multiple < self.config.asia_min_rr:
            return None
        if rr_multiple < self.config.min_rr:
            return None

        weak_trend = regime.strength == TrendStrength.WEAK
        marginal_rr = rr_multiple < 2.0
        tier_min_override = 0.01 if blocks["tier3"] else None
        lot_size = self.risk.calc_lot_size(ctx.account.balance, stop_distance_points, weak_trend=weak_trend, marginal_rr=marginal_rr, tier_min_override=tier_min_override)
        if self.risk.revenge_trade_detected(ctx.account, ctx.now, side, lot_size):
            return None

        return EntrySignal(
            timestamp=ctx.now,
            symbol=self.config.symbol,
            side=side,
            session=session,
            regime=regime,
            level=level,
            candle_type=candle,
            entry_price=current_price,
            stop_price=stop_price,
            stop_distance_points=stop_distance_points,
            lot_size=lot_size,
            tp_price=tp_price,
            rr_multiple=rr_multiple,
            spread_points=ctx.spread_points,
            tp_variant=tp_variant,
            reasons=[f"session={session.value}", f"regime={regime.direction.value}", f"strength={regime.strength.value}", f"level={level.label}", f"candle={candle.value}"],
            requires_manual_confirmation=(self.config.mode == Mode.SEMI_AUTO or session == SessionType.ASIA),
        )

    def _calc_stop(self, ctx: RuleContext, side: Side, level_price: float) -> tuple[float, int]:
        atr15 = float(ctx.m15["atr_14"].iloc[-1])
        buffer_points = max(self.config.stop_buffer_min, int(self.config.stop_buffer_atr_fraction * raw_points_from_price_move(atr15)))
        m15 = ctx.m15
        if side == Side.LONG:
            pivots = m15.loc[swing_lows(m15, 2, 2)]
            relevant = pivots[pivots["low"] <= level_price].tail(1)
            if relevant.empty:
                raise ValueError("No valid setup-associated swing low")
            structural = float(relevant["low"].iloc[-1])
            stop = structural - buffer_points * 0.01
            dist = raw_points_from_price_move(float(m15["close"].iloc[-1]) - stop)
        else:
            pivots = m15.loc[swing_highs(m15, 2, 2)]
            relevant = pivots[pivots["high"] >= level_price].tail(1)
            if relevant.empty:
                raise ValueError("No valid setup-associated swing high")
            structural = float(relevant["high"].iloc[-1])
            stop = structural + buffer_points * 0.01
            dist = raw_points_from_price_move(stop - float(m15["close"].iloc[-1]))
        return round(stop, 2), dist

    def _calc_tp(self, entry_price: float, stop_distance_points: int, levels: Sequence[Level], side: Side, variant: TPVariant, session: SessionType) -> tuple[float | None, float]:
        target = self.next_target_level(entry_price, levels, side, session, variant)
        stop_dist_price = stop_distance_points * 0.01
        if variant == TPVariant.B:
            tp = entry_price + (self.config.fixed_rr_variant_b * stop_dist_price if side == Side.LONG else -self.config.fixed_rr_variant_b * stop_dist_price)
            return round(tp, 2), self.config.fixed_rr_variant_b
        if not target:
            return None, 0.0
        reward_price = abs(target.price - entry_price)
        rr = reward_price / stop_dist_price if stop_dist_price else 0.0
        if variant == TPVariant.A:
            if rr < self.config.min_rr:
                return None, rr
            if rr <= self.config.max_rr_variant_a:
                tp = target.price - 0.10 if side == Side.LONG else target.price + 0.10
                return round(tp, 2), rr
            tp = entry_price + (self.config.max_rr_variant_a * stop_dist_price if side == Side.LONG else -self.config.max_rr_variant_a * stop_dist_price)
            return round(tp, 2), self.config.max_rr_variant_a
        if rr < self.config.min_rr:
            return None, rr
        return round(target.price, 2), rr
