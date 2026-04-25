from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import pandas as pd

from .config import SystemConfig
from .indicators import raw_points_from_price_move, swing_highs, swing_lows
from .models import Level, LevelTier


@dataclass(slots=True)
class LevelSet:
    levels: list[Level]

    def valid_for_entry(self, london_session: bool) -> list[Level]:
        out: list[Level] = []
        for level in self.levels:
            if not level.valid:
                continue
            if level.tier == LevelTier.TIER_3:
                continue
            if level.tier == LevelTier.TIER_2 and not london_session:
                continue
            out.append(level)
        return out


def _round_levels(close_prices: Iterable[float], step_price: float) -> list[float]:
    seen = set()
    out = []
    for price in close_prices:
        rounded = round(round(price / step_price) * step_price, 2)
        if rounded not in seen:
            seen.add(rounded)
            out.append(rounded)
    return out


class LevelDetector:
    def __init__(self, config: SystemConfig):
        self.config = config

    def detect(self, m15: pd.DataFrame, h1: pd.DataFrame) -> LevelSet:
        levels: list[Level] = []
        latest_time = h1.index[-1].to_pydatetime()

        # Tier 1 round numbers
        for price in _round_levels(h1["close"].tail(50).tolist(), self.config.round_number_step_price):
            levels.append(Level(price=price, tier=LevelTier.TIER_1, label=f"RN_{price:.2f}", source="round_number", reaction_points=0, retest_count=0, created_at=latest_time, last_test_at=latest_time))

        # Prior week high/low using UTC Monday-Friday window
        last_ts = h1.index[-1]
        week_start = (last_ts - pd.Timedelta(days=last_ts.weekday())).normalize()
        prior_week_start = week_start - pd.Timedelta(days=7)
        prior_week_end = week_start - pd.Timedelta(seconds=1)
        prior_week = h1.loc[(h1.index >= prior_week_start) & (h1.index <= prior_week_end)]
        if not prior_week.empty:
            levels.extend([
                Level(price=float(prior_week["high"].max()), tier=LevelTier.TIER_1, label="PRIOR_WEEK_HIGH", source="prior_week_high", reaction_points=0, retest_count=0, created_at=latest_time, last_test_at=latest_time),
                Level(price=float(prior_week["low"].min()), tier=LevelTier.TIER_1, label="PRIOR_WEEK_LOW", source="prior_week_low", reaction_points=0, retest_count=0, created_at=latest_time, last_test_at=latest_time),
            ])

        # Prior day high/low
        prior_day = m15[m15.index.date == (m15.index[-1] - pd.Timedelta(days=1)).date()]
        if not prior_day.empty:
            levels.extend([
                Level(price=float(prior_day["high"].max()), tier=LevelTier.TIER_2, label="PRIOR_DAY_HIGH", source="prior_day_high", reaction_points=0, retest_count=0, created_at=latest_time, last_test_at=latest_time, session_only="london_ny"),
                Level(price=float(prior_day["low"].min()), tier=LevelTier.TIER_2, label="PRIOR_DAY_LOW", source="prior_day_low", reaction_points=0, retest_count=0, created_at=latest_time, last_test_at=latest_time, session_only="london_ny"),
            ])

        # Confirmed swing pivots on H1 (tier1)
        h1_sw_high = swing_highs(h1, 3, 3)
        h1_sw_low = swing_lows(h1, 3, 3)
        levels.extend(self._levels_from_swings(h1, h1_sw_high, LevelTier.TIER_1, "h1_swing_high"))
        levels.extend(self._levels_from_swings(h1, h1_sw_low, LevelTier.TIER_1, "h1_swing_low"))

        # Confirmed swing pivots on M15 (tier2)
        m15_sw_high = swing_highs(m15, 2, 2)
        m15_sw_low = swing_lows(m15, 2, 2)
        levels.extend(self._levels_from_swings(m15, m15_sw_high, LevelTier.TIER_2, "m15_swing_high"))
        levels.extend(self._levels_from_swings(m15, m15_sw_low, LevelTier.TIER_2, "m15_swing_low"))

        deduped = self._dedupe(levels)
        self._annotate_tests_and_reactions(deduped, m15, h1)
        self._apply_staleness(deduped, h1)
        return LevelSet(deduped)

    def _levels_from_swings(self, df: pd.DataFrame, swing_mask: pd.Series, tier: LevelTier, source_prefix: str) -> list[Level]:
        points_needed = self.config.tier1_reaction_points if tier == LevelTier.TIER_1 else self.config.tier2_reaction_points
        result: list[Level] = []
        for ts, row in df[swing_mask].tail(20).iterrows():
            price = float(row["high"] if "high" in source_prefix else row["low"])
            result.append(Level(price=price, tier=tier, label=f"{source_prefix}_{ts.strftime('%Y%m%d%H%M')}", source=source_prefix, reaction_points=points_needed, retest_count=0, created_at=ts.to_pydatetime(), last_test_at=ts.to_pydatetime()))
        return result

    def _dedupe(self, levels: list[Level]) -> list[Level]:
        grouped: dict[tuple[LevelTier, int], Level] = {}
        for level in levels:
            key = (level.tier, round(level.price, 2).__hash__())
            if key not in grouped:
                grouped[key] = level
        return list(grouped.values())

    def _annotate_tests_and_reactions(self, levels: list[Level], m15: pd.DataFrame, h1: pd.DataFrame) -> None:
        for level in levels:
            source_df = h1 if level.tier == LevelTier.TIER_1 else m15
            tolerance = max(self.config.entry_zone_min_points, 0.25 * raw_points_from_price_move(float(source_df["close"].tail(14).std() or 0.3))) * 0.01
            touches = source_df[(source_df["low"] <= level.price + tolerance) & (source_df["high"] >= level.price - tolerance)]
            level.retest_count = int(len(touches))
            if not touches.empty:
                last_touch_idx = touches.index[-1]
                after = source_df.loc[last_touch_idx:].head(10)
                reaction = max(
                    abs(float(after["high"].max()) - level.price),
                    abs(float(after["low"].min()) - level.price),
                )
                level.reaction_points = raw_points_from_price_move(reaction)
                level.last_test_at = last_touch_idx.to_pydatetime()

    def _apply_staleness(self, levels: list[Level], h1: pd.DataFrame) -> None:
        atr_h1 = float(h1["atr_14"].iloc[-1]) if "atr_14" in h1.columns else float((h1["high"] - h1["low"]).tail(14).mean())
        current_close = float(h1["close"].iloc[-1])
        for level in levels:
            if level.last_test_at:
                sessions_since = (h1.index[-1].to_pydatetime() - level.last_test_at).days
                if sessions_since > self.config.level_stale_sessions:
                    level.valid = False
            if abs(current_close - level.price) > 0.5 * atr_h1 and ((current_close > level.price and level.source.endswith("high")) or (current_close < level.price and level.source.endswith("low"))):
                level.valid = False
