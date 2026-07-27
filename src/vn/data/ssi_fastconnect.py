# -*- coding: utf-8 -*-
"""SSI FastConnect v3 read-only market-data adapter.

This module intentionally exposes only authentication and market-data REST
calls. It does not import or expose SSI trading/account/private-key clients.
Tokens are cached in process memory only and are never written to disk.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping

import pandas as pd
import requests

_DEFAULT_API_URL = "https://api.ssi.com.vn"
_AUTH_PATH = "/api/v3/auth/token"
_OHLC_PATH = "/api/v3/data/ohlc"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
)
_SUPPORTED_PRICE_UNITS = {"thousand_vnd", "vnd"}
_TOKEN_EXPIRY_SKEW_SECONDS = 30


class SSIFastConnectError(RuntimeError):
    """Raised for a recoverable FastConnect configuration or API failure."""


@dataclass(frozen=True)
class _Credentials:
    api_url: str
    client_id: str
    api_key: str
    api_secret: str
    price_unit: str


@dataclass
class _Token:
    access_token: str
    expires_at: float


_token_lock = threading.Lock()
_token_cache: dict[tuple[str, str], _Token] = {}


def _env_first(*names: str) -> str:
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _credentials() -> _Credentials:
    price_unit = (os.getenv("VN_SSI_PRICE_UNIT") or "thousand_vnd").strip().lower()
    if price_unit not in _SUPPORTED_PRICE_UNITS:
        price_unit = "thousand_vnd"
    return _Credentials(
        api_url=(os.getenv("SSI_FASTCONNECT_API_URL") or _DEFAULT_API_URL).strip().rstrip("/"),
        client_id=_env_first("SSI_FASTCONNECT_CLIENT_ID", "SSI_CLIENT_ID"),
        api_key=_env_first("SSI_FASTCONNECT_API_KEY", "SSI_API_KEY"),
        api_secret=_env_first("SSI_FASTCONNECT_API_SECRET", "SSI_API_SECRET"),
        price_unit=price_unit,
    )


def is_configured() -> bool:
    """Return whether read-only market-data credentials are available."""
    credentials = _credentials()
    return bool(credentials.api_key and credentials.api_secret)


def get_status() -> dict[str, Any]:
    """Return a secret-safe provider status payload."""
    credentials = _credentials()
    return {
        "provider": "ssi_fastconnect_v3",
        "configured": bool(credentials.api_key and credentials.api_secret),
        "mode": "market_data_read_only",
        "apiUrl": credentials.api_url,
        "priceUnit": credentials.price_unit,
    }


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _payload_data(payload: Any) -> Any:
    if isinstance(payload, Mapping) and "data" in payload:
        return payload.get("data")
    return payload


def _parse_expires_at(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return time.time() + 3300
    # SSI currently documents epoch seconds. Keep a conservative fallback for
    # providers returning a relative duration instead of an absolute timestamp.
    if parsed <= time.time() - 60:
        return time.time() + max(parsed, 300)
    return parsed


def _authenticate(credentials: _Credentials, session: Any, timeout: float) -> str:
    if not credentials.api_key or not credentials.api_secret:
        raise SSIFastConnectError("SSI FastConnect market-data credentials are not configured")

    cache_key = (credentials.api_url, credentials.api_key)
    with _token_lock:
        cached = _token_cache.get(cache_key)
        if cached and time.time() < cached.expires_at - _TOKEN_EXPIRY_SKEW_SECONDS:
            return cached.access_token

        response = session.post(
            f"{credentials.api_url}{_AUTH_PATH}",
            json={"apiKey": credentials.api_key, "apiSecret": credentials.api_secret},
            headers=_headers(),
            timeout=timeout,
        )
        response.raise_for_status()
        payload = _payload_data(response.json())
        if not isinstance(payload, Mapping):
            raise SSIFastConnectError("SSI authentication returned an unexpected payload")
        access_token = str(payload.get("accessToken") or "").strip()
        if not access_token:
            raise SSIFastConnectError("SSI authentication response is missing accessToken")
        token = _Token(
            access_token=access_token,
            expires_at=_parse_expires_at(payload.get("expiresAt")),
        )
        _token_cache[cache_key] = token
        return token.access_token


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_price(value: Any, source_unit: str) -> float | None:
    parsed = _float(value)
    if parsed is None:
        return None
    if source_unit == "vnd":
        return parsed / 1000.0
    return parsed


def _normalize_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:10].replace("/", "-")


def _rate_limit_headers(headers: Mapping[str, Any]) -> dict[str, str | None]:
    lowered = {str(key).lower(): str(value) for key, value in headers.items()}
    return {
        "limit": lowered.get("x-ratelimit-limit"),
        "remaining": lowered.get("x-ratelimit-remaining"),
        "reset": lowered.get("x-ratelimit-reset"),
    }


def _empty_frame(*, warning: str | None = None) -> pd.DataFrame:
    frame = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "value"])
    frame.attrs.update(
        {
            "source": "ssi_fastconnect_v3",
            "price_unit": "thousand_vnd",
            "warning": warning,
        }
    )
    return frame


def fetch_daily_bars(
    ticker: str,
    days: int = 260,
    timeout: float = 12.0,
    *,
    session: Any | None = None,
) -> pd.DataFrame:
    """Fetch SSI v3 daily OHLCV normalized to thousand-VND prices.

    The function raises ``SSIFastConnectError`` for configuration/contract
    problems and lets request exceptions propagate. The provider facade catches
    those failures and falls back to VNDIRECT.
    """
    symbol = ticker.strip().upper()
    if not symbol:
        return _empty_frame(warning="empty_symbol")
    requested_days = max(1, min(int(days), 1000))
    credentials = _credentials()
    client = session or requests.Session()
    token = _authenticate(credentials, client, timeout)

    now = datetime.now()
    from_date = now - timedelta(days=max(requested_days * 2, 365))
    params = {
        "symbol": symbol,
        "from": from_date.strftime("%Y/%m/%d 00:00:00"),
        "to": now.strftime("%Y/%m/%d 23:59:59"),
        "timeFrame": "1d",
        "pageIndex": 1,
        "pageSize": min(max(requested_days, 100), 1000),
    }
    response = client.get(
        f"{credentials.api_url}{_OHLC_PATH}",
        params=params,
        headers=_headers(token),
        timeout=timeout,
    )
    response.raise_for_status()
    payload = _payload_data(response.json())
    if not isinstance(payload, list):
        raise SSIFastConnectError("SSI OHLC response is not a data list")

    records: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, Mapping):
            continue
        record = {
            "date": _normalize_date(row.get("tradingDate")),
            "open": _normalize_price(row.get("open"), credentials.price_unit),
            "high": _normalize_price(row.get("high"), credentials.price_unit),
            "low": _normalize_price(row.get("low"), credentials.price_unit),
            "close": _normalize_price(row.get("close"), credentials.price_unit),
            "volume": _float(row.get("volume")),
            "value": _float(row.get("value")),
        }
        if record["date"]:
            records.append(record)

    if not records:
        frame = _empty_frame(warning="no_ohlcv_data")
        frame.attrs["rate_limit"] = _rate_limit_headers(response.headers)
        return frame

    frame = pd.DataFrame(records)
    for column in ("open", "high", "low", "close", "volume", "value"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = (
        frame.dropna(subset=["date", "open", "high", "low", "close"])
        .drop_duplicates(subset=["date"], keep="last")
        .sort_values("date")
        .tail(requested_days)
        .reset_index(drop=True)
    )
    frame.attrs.update(
        {
            "source": "ssi_fastconnect_v3",
            "price_unit": "thousand_vnd",
            "source_price_unit": credentials.price_unit,
            "rate_limit": _rate_limit_headers(response.headers),
        }
    )
    return frame


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def fetch_index_summary(
    index: str = "VNINDEX",
    timeout: float = 12.0,
    *,
    session: Any | None = None,
) -> dict[str, Any]:
    """Fetch official SSI index breadth/turnover data for market overview."""
    index_code = index.strip().upper()
    if not index_code:
        return {}
    credentials = _credentials()
    client = session or requests.Session()
    token = _authenticate(credentials, client, timeout)
    response = client.get(
        f"{credentials.api_url}/api/v3/data/indexSummary",
        params={"index": index_code},
        headers=_headers(token),
        timeout=timeout,
    )
    response.raise_for_status()
    payload = _payload_data(response.json())
    if isinstance(payload, Mapping):
        rows = [payload]
    elif isinstance(payload, list):
        rows = payload
    else:
        raise SSIFastConnectError("SSI index summary response has an unexpected payload")
    row = next((item for item in rows if isinstance(item, Mapping)), None)
    if row is None:
        return {}
    return {
        "index": index_code,
        "tradingDate": _normalize_date(row.get("tradingDate")),
        "indexValue": _float(row.get("indexValue")),
        "changePct": _float(row.get("indexChangePercentage")),
        "advancers": _int(row.get("totalAdvanceStock")),
        "decliners": _int(row.get("totalDeclineStock")),
        "unchanged": _int(row.get("totalNoChangeStock")),
        "ceiling": _int(row.get("totalCeilingStock")),
        "floor": _int(row.get("totalFloorStock")),
        "totalValue": _float(row.get("totalMatchValue")),
        "source": "ssi_fastconnect_v3",
    }


def clear_token_cache() -> None:
    """Clear in-memory authentication state (mainly for tests/credential rotation)."""
    with _token_lock:
        _token_cache.clear()
