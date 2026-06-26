# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

_REQUIRED_COLUMNS = {"open", "high", "low", "close"}


def _as_float(value: Any) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    result = 100 - (100 / (1 + rs))
    result = result.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    result = result.mask((avg_loss == 0) & (avg_gain == 0), 50.0)
    return result


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add the VN T+ indicator stack to an OHLCV dataframe."""
    if df is None or df.empty:
        return pd.DataFrame()
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"missing OHLC columns: {sorted(missing)}")

    out = df.copy()
    if "date" in out.columns:
        out = out.sort_values("date")
    out = out.reset_index(drop=True)

    for column in ["open", "high", "low", "close", "volume"]:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")

    close = out["close"]
    out["EMA20"] = close.ewm(span=20, adjust=False, min_periods=20).mean()
    out["EMA60"] = close.ewm(span=60, adjust=False, min_periods=60).mean()
    out["MA50"] = close.rolling(window=50, min_periods=50).mean()
    out["MA200"] = close.rolling(window=200, min_periods=200).mean()
    out["RSI14"] = _rsi(close, 14)

    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    out["MACD"] = ema12 - ema26
    out["MACD_SIGNAL"] = out["MACD"].ewm(span=9, adjust=False, min_periods=9).mean()
    out["MACD_HIST"] = out["MACD"] - out["MACD_SIGNAL"]

    if "volume" in out.columns:
        out["VOL20"] = out["volume"].rolling(window=20, min_periods=20).mean()
        out["VOLUME_RATIO"] = out["volume"] / out["VOL20"].replace(0, pd.NA)
    else:
        out["VOL20"] = pd.NA
        out["VOLUME_RATIO"] = pd.NA

    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            (out["high"] - out["low"]).abs(),
            (out["high"] - previous_close).abs(),
            (out["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["ATR14"] = true_range.rolling(window=14, min_periods=14).mean()
    return out


def latest_technical_snapshot(df: pd.DataFrame) -> Dict[str, Optional[float]]:
    """Return the latest row using frontend/API camelCase keys."""
    if df is None or df.empty:
        return {}
    latest = df.iloc[-1]
    return {
        "close": _as_float(latest.get("close")),
        "ema20": _as_float(latest.get("EMA20")),
        "ema60": _as_float(latest.get("EMA60")),
        "ma50": _as_float(latest.get("MA50")),
        "ma200": _as_float(latest.get("MA200")),
        "rsi14": _as_float(latest.get("RSI14")),
        "macd": _as_float(latest.get("MACD")),
        "macdSignal": _as_float(latest.get("MACD_SIGNAL")),
        "macdHist": _as_float(latest.get("MACD_HIST")),
        "volume": _as_float(latest.get("volume")),
        "vol20": _as_float(latest.get("VOL20")),
        "volumeRatio": _as_float(latest.get("VOLUME_RATIO")),
        "atr14": _as_float(latest.get("ATR14")),
    }
