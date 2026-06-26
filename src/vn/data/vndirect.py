# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pandas as pd
import requests

_DCHART_URL = "https://dchart-api.vndirect.com.vn/dchart/history"
_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Referer": "https://dchart.vndirect.com.vn/",
}


def _normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def _to_records(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    times = payload.get("t") or []
    opens = payload.get("o") or []
    highs = payload.get("h") or []
    lows = payload.get("l") or []
    closes = payload.get("c") or []
    volumes = payload.get("v") or []
    records: List[Dict[str, Any]] = []
    for i, timestamp in enumerate(times):
        try:
            records.append(
                {
                    "date": datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date().isoformat(),
                    "open": opens[i],
                    "high": highs[i],
                    "low": lows[i],
                    "close": closes[i],
                    "volume": volumes[i] if i < len(volumes) else None,
                }
            )
        except (IndexError, TypeError, ValueError):
            continue
    return records


def fetch_ohlcv(ticker: str, days: int = 260, timeout: int = 15) -> pd.DataFrame:
    """Fetch daily OHLCV from VNDIRECT dchart.

    Returns an empty DataFrame on recoverable network/source failures.
    """
    symbol = _normalize_ticker(ticker)
    if not symbol:
        return pd.DataFrame()
    to_ts = int(datetime.now(tz=timezone.utc).timestamp())
    from_ts = int((datetime.now(tz=timezone.utc) - timedelta(days=max(days * 2, 365))).timestamp())
    params = {
        "resolution": "D",
        "symbol": symbol,
        "from": from_ts,
        "to": to_ts,
    }
    try:
        response = requests.get(_DCHART_URL, params=params, headers=_HEADERS, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return pd.DataFrame()
    records = _to_records(payload)
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"]).tail(days).reset_index(drop=True)
