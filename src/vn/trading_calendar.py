"""Versioned Vietnam equity trading calendar with an explicit fallback marker.

The exchange holiday set is intentionally kept in code as a small, reviewable
versioned dataset. Unknown years use weekday-only fallback and are marked
estimated so callers cannot present a calendar approximation as exchange truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import FrozenSet


@dataclass(frozen=True)
class VNSettlementInfo:
    settlement_date: date
    estimated: bool
    calendar_version: str


# Official HOSE 2026 notice also applies to the common equity trading calendar:
# https://www.hsx.vn/vi/tin-tuc/hose-thong-bao-lich-nghi-giao-dich-nam-2026/2437411
# HNX publishes the corresponding market notice at:
# https://hnx.vn/vi-vn/chi-tiet-lich-nghi-gd-60021971.html?_page=1
_KNOWN_HOLIDAYS: dict[int, FrozenSet[date]] = {
    2026: frozenset(
        {
            date(2026, 1, 1),
            date(2026, 1, 2),
            date(2026, 2, 16),
            date(2026, 2, 17),
            date(2026, 2, 18),
            date(2026, 2, 19),
            date(2026, 2, 20),
            date(2026, 4, 27),
            date(2026, 4, 30),
            date(2026, 5, 1),
            date(2026, 8, 31),
            date(2026, 9, 1),
            date(2026, 9, 2),
        }
    ),
}


_SUPPORTED_EXCHANGES = {"hose", "hnx", "upcom", "vn"}


def _normalize_exchange(exchange: str) -> str:
    normalized = str(exchange or "vn").strip().lower()
    if normalized not in _SUPPORTED_EXCHANGES:
        raise ValueError(f"unsupported Vietnam exchange: {exchange}")
    return normalized


def _calendar_for(year: int) -> tuple[FrozenSet[date], bool, str]:
    holidays = _KNOWN_HOLIDAYS.get(year)
    if holidays is None:
        return frozenset(), True, "weekday-fallback"
    return holidays, False, "hose-hnx-2026-v1"


def is_vn_trading_day(day: date, *, exchange: str = "vn") -> bool:
    _normalize_exchange(exchange)
    holidays, _, _ = _calendar_for(day.year)
    return day.weekday() < 5 and day not in holidays


def add_vn_trading_days(start: date, trading_days: int, *, exchange: str = "vn") -> VNSettlementInfo:
    _normalize_exchange(exchange)
    remaining = max(0, int(trading_days))
    current = start
    holidays, estimated, version = _calendar_for(start.year)
    while remaining:
        current += timedelta(days=1)
        # A date can cross into a year whose calendar is not versioned. Resolve
        # the target year each iteration rather than reusing start-year data.
        if current.weekday() >= 5:
            continue
        target_holidays, target_estimated, target_version = _calendar_for(current.year)
        if current in target_holidays:
            continue
        remaining -= 1
        estimated = estimated or target_estimated
        if target_version != version:
            version = "mixed-calendar-estimated"
    return VNSettlementInfo(current, estimated, version)


def vn_settlement_info(
    trade_date: date,
    *,
    trading_days: int = 2,
    exchange: str = "vn",
) -> VNSettlementInfo:
    return add_vn_trading_days(trade_date, trading_days, exchange=exchange)
