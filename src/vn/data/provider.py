# -*- coding: utf-8 -*-
from __future__ import annotations

import os

import pandas as pd

from src.vn.data import dnse_openapi, ssi_fastconnect, ssi_iboard, vndirect

_SUPPORTED_PROVIDERS = {"auto", "dnse", "dnse_openapi", "ssi_fastconnect", "vndirect"}


def _configured_provider() -> str:
    configured = (os.getenv("VN_MARKET_DATA_PROVIDER") or "auto").strip().lower()
    return configured if configured in _SUPPORTED_PROVIDERS else "auto"


def _mark_vndirect(frame: pd.DataFrame, *, fallback_from: str | None = None) -> pd.DataFrame:
    if frame is None:
        frame = pd.DataFrame()
    frame.attrs["source"] = "vndirect"
    frame.attrs["price_unit"] = "thousand_vnd"
    if fallback_from:
        frame.attrs["fallback_from"] = fallback_from
    return frame


def _mark_fallback(frame: pd.DataFrame, attempted: list[str]) -> pd.DataFrame:
    if attempted:
        frame.attrs["fallback_from"] = ",".join(attempted)
    return frame


def _provider_chain(mode: str) -> list[str]:
    if mode in {"dnse", "dnse_openapi"}:
        return ["dnse_openapi", "ssi_fastconnect_v3", "vndirect"]
    if mode == "ssi_fastconnect":
        return ["ssi_fastconnect_v3", "vndirect"]
    if mode == "vndirect":
        return ["vndirect"]

    chain: list[str] = []
    if dnse_openapi.is_configured():
        chain.append("dnse_openapi")
    if ssi_fastconnect.is_configured():
        chain.append("ssi_fastconnect_v3")
    chain.append("vndirect")
    return chain


def get_daily_bars(ticker: str, days: int = 260) -> pd.DataFrame:
    """Return VN daily bars through the configured fail-soft provider chain.

    ``auto`` prefers DNSE OpenAPI, then SSI FastConnect when their read-only
    credentials are configured, and finally VNDIRECT. Explicit broker modes are
    still fail-soft so a temporary outage does not take down the analysis path.
    """
    chain = _provider_chain(_configured_provider())
    attempted: list[str] = []
    for source in chain:
        if source == "dnse_openapi":
            if not dnse_openapi.is_configured():
                attempted.append(source)
                continue
            try:
                frame = dnse_openapi.fetch_daily_bars(ticker, days=days)
            except Exception:
                frame = pd.DataFrame()
        elif source == "ssi_fastconnect_v3":
            if not ssi_fastconnect.is_configured():
                attempted.append(source)
                continue
            try:
                frame = ssi_fastconnect.fetch_daily_bars(ticker, days=days)
            except Exception:
                frame = pd.DataFrame()
        else:
            frame = _mark_vndirect(vndirect.fetch_ohlcv(ticker, days=days))

        if frame is not None and not frame.empty:
            return _mark_fallback(frame, attempted)
        attempted.append(source)

    return _mark_vndirect(pd.DataFrame(), fallback_from=",".join(attempted[:-1]) or None)


def get_exchange_breadth(exchange: str = "hose") -> dict:
    """Return official SSI index summary with SSI iBoard fallback.

    DNSE OpenAPI currently exposes OHLC/trade streams but no aggregate exchange
    breadth contract, so DNSE is not forced into this path.
    """
    mode = _configured_provider()
    should_try_ssi = mode in {"auto", "dnse", "dnse_openapi", "ssi_fastconnect"} and ssi_fastconnect.is_configured()
    if should_try_ssi:
        try:
            summary = ssi_fastconnect.fetch_index_summary("VNINDEX")
        except Exception:
            summary = {}
        if summary:
            return summary
    fallback = ssi_iboard.fetch_exchange_breadth(exchange)
    if should_try_ssi and fallback:
        fallback["fallback_from"] = "ssi_fastconnect_v3"
    return fallback


def get_provider_status() -> dict:
    """Return effective VN market-data configuration without secrets."""
    mode = _configured_provider()
    chain = _provider_chain(mode)
    effective_primary = chain[0]
    return {
        "configuredProvider": mode,
        "effectivePrimary": effective_primary,
        "fallback": chain[1] if len(chain) > 1 else None,
        "fallbackChain": chain[1:],
        "dnseOpenAPI": dnse_openapi.get_status(),
        "ssiFastConnect": ssi_fastconnect.get_status(),
        "breadthPrimary": "ssi_fastconnect_v3" if ssi_fastconnect.is_configured() else "ssi_iboard",
        "executionEnabled": False,
    }
