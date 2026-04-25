from __future__ import annotations

import numpy as np
import pandas as pd


def ensure_time_index(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "time" in out.columns:
        out["time"] = pd.to_datetime(out["time"], utc=True)
        out = out.sort_values("time").set_index("time")
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC")
    return out


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)

    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)

    atr_smoothed = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_smoothed)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_smoothed)
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    return dx.ewm(alpha=1 / period, adjust=False).mean().fillna(0.0)


def swing_highs(df: pd.DataFrame, left: int, right: int) -> pd.Series:
    highs = df["high"]
    out = pd.Series(False, index=df.index)
    for i in range(left, len(df) - right):
        center = highs.iloc[i]
        if center == highs.iloc[i - left : i + right + 1].max() and center > highs.iloc[i - left : i].max() and center >= highs.iloc[i + 1 : i + right + 1].max():
            out.iloc[i] = True
    return out


def swing_lows(df: pd.DataFrame, left: int, right: int) -> pd.Series:
    lows = df["low"]
    out = pd.Series(False, index=df.index)
    for i in range(left, len(df) - right):
        center = lows.iloc[i]
        if center == lows.iloc[i - left : i + right + 1].min() and center < lows.iloc[i - left : i].min() and center <= lows.iloc[i + 1 : i + right + 1].min():
            out.iloc[i] = True
    return out


def add_common_indicators(df: pd.DataFrame, ema_fast: int = 20, ema_slow: int = 50, atr_period: int = 14, adx_period: int = 14) -> pd.DataFrame:
    out = ensure_time_index(df)
    out[f"ema_{ema_fast}"] = ema(out["close"], ema_fast)
    out[f"ema_{ema_slow}"] = ema(out["close"], ema_slow)
    out[f"atr_{atr_period}"] = atr(out, atr_period)
    out[f"adx_{adx_period}"] = adx(out, adx_period)
    return out


def raw_points_from_price_move(price_move: float) -> int:
    return int(round(price_move / 0.01))
