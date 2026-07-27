# -*- coding: utf-8 -*-
"""DNSE OpenAPI read-only market-data adapter.

Only HMAC-authenticated market-data GET endpoints are exposed here. Account,
OTP, trading-token and order mutation endpoints are intentionally absent.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from typing import Any, Mapping

import pandas as pd
import requests

_DEFAULT_API_URL = "https://openapi.dnse.com.vn"
_OHLC_PATH = "/price/ohlc"
_SUPPORTED_PRICE_UNITS = {"thousand_vnd", "vnd"}
_WS_URL = "wss://ws-openapi.dnse.com.vn/v1/stream?encoding=json"
_WS_CONTROL_ACTIONS = {
    "welcome",
    "auth_success",
    "subscribed",
    "unsubscribed",
    "ping",
    "pong",
    "connection_expired",
    "error",
}
_INDEX_SYMBOLS = {
    "VNINDEX",
    "VN30",
    "VN100",
    "VNMIDCAP",
    "VNSML",
    "HNXINDEX",
    "HNX30",
    "UPCOMINDEX",
}


class DNSEOpenAPIError(RuntimeError):
    """Raised for DNSE configuration or market-data contract failures."""


@dataclass(frozen=True)
class _Credentials:
    api_url: str
    api_key: str
    api_secret: str
    price_unit: str


def _credentials() -> _Credentials:
    price_unit = (os.getenv("VN_DNSE_PRICE_UNIT") or "thousand_vnd").strip().lower()
    if price_unit not in _SUPPORTED_PRICE_UNITS:
        price_unit = "thousand_vnd"
    return _Credentials(
        api_url=(os.getenv("DNSE_BASE_URL") or _DEFAULT_API_URL).strip().rstrip("/"),
        api_key=(os.getenv("DNSE_API_KEY") or "").strip(),
        api_secret=(os.getenv("DNSE_API_SECRET") or "").strip(),
        price_unit=price_unit,
    )


def is_configured() -> bool:
    credentials = _credentials()
    return bool(credentials.api_key and credentials.api_secret)


def get_status() -> dict[str, Any]:
    credentials = _credentials()
    return {
        "provider": "dnse_openapi",
        "configured": bool(credentials.api_key and credentials.api_secret),
        "mode": "market_data_read_only",
        "apiUrl": credentials.api_url,
        "priceUnit": credentials.price_unit,
        "restOhlc": True,
        "websocket": True,
        "websocketTransport": "native_protocol",
    }


def _websocket_auth_message(
    credentials: _Credentials,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, Any]:
    """Build current DNSE WebSocket auth; nonce must be a string."""
    if not credentials.api_key or not credentials.api_secret:
        raise DNSEOpenAPIError("DNSE market-data credentials are not configured")
    ts = int(time.time()) if timestamp is None else int(timestamp)
    nonce_value = nonce or str(int(time.time() * 1_000_000))
    message = f"{credentials.api_key}:{ts}:{nonce_value}"
    signature = hmac.new(
        credentials.api_secret.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()
    return {
        "action": "auth",
        "api_key": credentials.api_key,
        "signature": signature,
        "timestamp": ts,
        "nonce": nonce_value,
    }


def _websocket_subscribe_message(symbol: str) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    return {
        "action": "subscribe",
        "channels": [
            {"name": "tick.G1.json", "symbols": [symbol]},
            {"name": "top_price.G1.json", "symbols": [symbol]},
            {"name": "ohlc.1.json", "symbols": [symbol]},
        ],
    }


async def capture_market_stream(
    ticker: str,
    seconds: int = 30,
    *,
    websocket_url: str = _WS_URL,
) -> dict[str, Any]:
    """Capture a bounded read-only DNSE stream using the current protocol."""
    try:
        import websockets
    except ImportError as exc:
        raise DNSEOpenAPIError("websockets package is required for DNSE stream") from exc

    symbol = ticker.strip().upper()
    if not symbol:
        raise DNSEOpenAPIError("DNSE stream symbol is empty")
    credentials = _credentials()
    counts = {"trade": 0, "quote": 0, "ohlc": 0, "other": 0}
    latest: dict[str, Any] = {}
    controls: list[str] = []
    started = time.monotonic()
    rate_limit: Mapping[str, Any] = {}

    async with websockets.connect(websocket_url, ssl=True) as ws:
        welcome = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        if welcome.get("action") != "welcome":
            raise DNSEOpenAPIError("DNSE stream did not return welcome")
        await ws.send(json.dumps(_websocket_auth_message(credentials)))
        auth = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        if auth.get("action") != "auth_success":
            raise DNSEOpenAPIError(
                f"DNSE stream authentication failed: {auth.get('code') or auth.get('action')}"
            )
        controls.append("auth_success")
        if isinstance(auth.get("rate_limit"), Mapping):
            rate_limit = auth["rate_limit"]
        await ws.send(json.dumps(_websocket_subscribe_message(symbol)))

        duration = max(1, min(int(seconds), 120))
        while time.monotonic() - started < duration:
            remaining = max(0.1, duration - (time.monotonic() - started))
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(5.0, remaining))
            except asyncio.TimeoutError:
                continue
            data = json.loads(raw)
            action = data.get("action")
            if action in _WS_CONTROL_ACTIONS:
                controls.append(str(action))
                if action == "ping":
                    await ws.send(json.dumps({"action": "pong", "timestamp": data.get("timestamp")}))
                elif action == "error":
                    raise DNSEOpenAPIError(
                        f"DNSE stream error: {data.get('code') or data.get('message')}"
                    )
                continue

            message_type = str(data.get("T") or "")
            if message_type in {"t", "te"}:
                bucket = "trade"
            elif message_type == "q":
                bucket = "quote"
            elif message_type == "b":
                bucket = "ohlc"
            else:
                bucket = "other"
            counts[bucket] += 1
            normalized = {
                key: data.get(key)
                for key in (
                    "T",
                    "symbol",
                    "matchPrice",
                    "matchQtty",
                    "side",
                    "bidPrice",
                    "askPrice",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "time",
                    "timestamp",
                )
                if key in data
            }
            if bucket == "quote":
                bids = data.get("bid") if isinstance(data.get("bid"), list) else []
                offers = data.get("offer") if isinstance(data.get("offer"), list) else []
                normalized["bestBid"] = bids[0] if bids else None
                normalized["bestAsk"] = offers[0] if offers else None
                normalized["bidLevels"] = bids
                normalized["askLevels"] = offers
            latest[bucket] = normalized

    return {
        "ok": sum(counts.values()) > 0,
        "seconds": seconds,
        "counts": counts,
        "latest": latest,
        "controls": controls,
        "rateLimit": dict(rate_limit),
    }


def _signature_headers(
    method: str,
    path: str,
    credentials: _Credentials,
    *,
    now: datetime | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Build DNSE HMAC-SHA256 headers using the official SDK contract."""
    if not credentials.api_key or not credentials.api_secret:
        raise DNSEOpenAPIError("DNSE market-data credentials are not configured")
    timestamp = now or datetime.now(timezone.utc)
    date_value = format_datetime(timestamp.astimezone(timezone.utc))
    nonce_value = nonce or uuid.uuid4().hex
    date_header = "x-aux-date"
    signed_headers = f"(request-target) {date_header}"
    signature_input = "\n".join(
        [
            f"(request-target): {method.lower()} {path}",
            f"{date_header}: {date_value}",
            f"nonce: {nonce_value}",
        ]
    )
    digest = hmac.new(
        credentials.api_secret.encode(),
        signature_input.encode(),
        hashlib.sha256,
    ).digest()
    encoded = urllib.parse.quote(base64.b64encode(digest).decode(), safe="")
    signature = (
        f'Signature keyId="{credentials.api_key}",algorithm="hmac-sha256",'
        f'headers="{signed_headers}",signature="{encoded}",nonce="{nonce_value}"'
    )
    return {
        "Accept": "application/json",
        "X-API-Key": credentials.api_key,
        "X-Aux-Date": date_value,
        "X-Signature": signature,
    }


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _normalize_price(value: Any, source_unit: str) -> float | None:
    parsed = _float(value)
    if parsed is None:
        return None
    return parsed / 1000.0 if source_unit == "vnd" else parsed


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
            "source": "dnse_openapi",
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
    """Fetch DNSE daily OHLCV and normalize prices to thousand VND."""
    symbol = ticker.strip().upper()
    if not symbol:
        return _empty_frame(warning="empty_symbol")
    requested_days = max(1, min(int(days), 1500))
    credentials = _credentials()
    now = datetime.now(timezone.utc)
    from_ts = int((now - timedelta(days=max(requested_days * 2, 365))).timestamp())
    params = {
        "symbol": symbol,
        "type": "INDEX" if symbol in _INDEX_SYMBOLS else "STOCK",
        "resolution": "1D",
        "from": str(from_ts),
        "to": str(int(now.timestamp())),
    }
    client = session or requests.Session()
    response = client.get(
        f"{credentials.api_url}{_OHLC_PATH}",
        params=params,
        headers=_signature_headers("GET", _OHLC_PATH, credentials),
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, Mapping):
        raise DNSEOpenAPIError("DNSE OHLC response is not an object")

    times = payload.get("t") or []
    opens = payload.get("o") or []
    highs = payload.get("h") or []
    lows = payload.get("l") or []
    closes = payload.get("c") or []
    volumes = payload.get("v") or []
    if not isinstance(times, list):
        raise DNSEOpenAPIError("DNSE OHLC response has invalid timestamp array")

    records: list[dict[str, Any]] = []
    for index, timestamp in enumerate(times):
        try:
            record = {
                "date": datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date().isoformat(),
                "open": _normalize_price(opens[index], credentials.price_unit),
                "high": _normalize_price(highs[index], credentials.price_unit),
                "low": _normalize_price(lows[index], credentials.price_unit),
                "close": _normalize_price(closes[index], credentials.price_unit),
                "volume": _int(volumes[index]) if index < len(volumes) else None,
                "value": None,
            }
        except (IndexError, TypeError, ValueError):
            continue
        records.append(record)

    if not records:
        frame = _empty_frame(warning="no_ohlcv_data")
        frame.attrs["rate_limit"] = _rate_limit_headers(response.headers)
        return frame

    frame = pd.DataFrame(records)
    for column in ["open", "high", "low", "close", "volume", "value"]:
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
            "source": "dnse_openapi",
            "price_unit": "thousand_vnd",
            "source_price_unit": credentials.price_unit,
            "rate_limit": _rate_limit_headers(response.headers),
            "next_time": payload.get("nextTime"),
        }
    )
    return frame


def fetch_latest_trade(
    ticker: str,
    timeout: float = 10.0,
    *,
    session: Any | None = None,
) -> dict[str, Any]:
    """Fetch the latest round-lot trade snapshot without OTP."""
    symbol = ticker.strip().upper()
    if not symbol:
        return {}
    credentials = _credentials()
    path = f"/price/{symbol}/trades/latest"
    client = session or requests.Session()
    response = client.get(
        f"{credentials.api_url}{path}",
        params={"boardId": "G1"},
        headers=_signature_headers("GET", path, credentials),
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("trades") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], Mapping):
        return {}
    row = rows[0]
    raw_total_volume = _int(row.get("totalVolumeTraded"))
    gross_amount_billion = _float(row.get("grossTradeAmount"))
    return {
        "symbol": str(row.get("symbol") or symbol),
        "price": _normalize_price(row.get("matchPrice"), credentials.price_unit),
        "matchVolume": _int(row.get("matchQtty")),
        "side": row.get("side"),
        "avgPrice": _normalize_price(row.get("avgPrice"), credentials.price_unit),
        # Live production evidence on 2026-07-27 showed the trade snapshot's
        # cumulative volume in 10-share units and gross amount in billion VND.
        # Preserve raw fields and expose normalized estimates explicitly.
        "totalVolumeRaw": raw_total_volume,
        "totalVolumeShares": raw_total_volume * 10 if raw_total_volume is not None else None,
        "grossTradeAmountBillionVnd": gross_amount_billion,
        "totalValueVnd": round(gross_amount_billion * 1_000_000_000, 3) if gross_amount_billion is not None else None,
        "high": _normalize_price(row.get("highestPrice"), credentials.price_unit),
        "low": _normalize_price(row.get("lowestPrice"), credentials.price_unit),
        "open": _normalize_price(row.get("openPrice"), credentials.price_unit),
        "time": row.get("time"),
        "source": "dnse_openapi",
    }
