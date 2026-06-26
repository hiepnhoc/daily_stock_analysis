# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, Iterable

import requests

_BASE_URL = "https://iboard-query.ssi.com.vn"
_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Referer": "https://iboard.ssi.com.vn/",
}


def _rows(payload: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return
    if isinstance(payload, dict):
        for key in ("data", "items", "stocks", "stockList"):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        yield item
                return
        # Some endpoints return a dict keyed by symbol.
        for value in payload.values():
            if isinstance(value, dict):
                yield value


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_live_quote(ticker: str, timeout: int = 10) -> Dict[str, Any]:
    symbol = ticker.strip().upper()
    if not symbol:
        return {}
    try:
        response = requests.get(f"{_BASE_URL}/stock/{symbol}", headers=_HEADERS, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return {}
    row = next(iter(_rows(payload)), payload if isinstance(payload, dict) else {})
    if not isinstance(row, dict):
        return {}
    return {
        "ticker": symbol,
        "price": _float(row.get("matchedPrice")),
        "changePct": _float(row.get("priceChangePercent")),
        "volume": _float(row.get("nmTotalTradedQty") or row.get("stockVol")),
        "value": _float(row.get("nmTotalTradedValue")),
        "refPrice": _float(row.get("refPrice")),
        "tradingDate": row.get("tradingDate"),
        "session": row.get("session") or row.get("exchangeSession"),
        "source": "ssi_iboard",
    }


def fetch_exchange_breadth(exchange: str = "hose", timeout: int = 10) -> Dict[str, Any]:
    try:
        response = requests.get(f"{_BASE_URL}/stock/exchange/{exchange.lower()}", headers=_HEADERS, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return {}

    advancers = decliners = ceiling = floor = unchanged = 0
    total_value = 0.0
    for row in _rows(payload):
        symbol = row.get("stockSymbol") or row.get("symbol")
        if not symbol:
            continue
        change_pct = _float(row.get("priceChangePercent"))
        if change_pct is None:
            change = _float(row.get("priceChange"))
            change_pct = change
        if change_pct is None or change_pct == 0:
            unchanged += 1
        elif change_pct > 0:
            advancers += 1
        else:
            decliners += 1
        matched = _float(row.get("matchedPrice"))
        ceiling_price = _float(row.get("ceiling"))
        floor_price = _float(row.get("floor"))
        if matched is not None and ceiling_price is not None and matched >= ceiling_price:
            ceiling += 1
        if matched is not None and floor_price is not None and matched <= floor_price:
            floor += 1
        total_value += _float(row.get("nmTotalTradedValue")) or 0.0

    if advancers == decliners == ceiling == floor == unchanged == 0:
        return {}
    return {
        "advancers": advancers,
        "decliners": decliners,
        "ceiling": ceiling,
        "floor": floor,
        "unchanged": unchanged,
        "totalValue": total_value or None,
        "source": "ssi_iboard",
    }
