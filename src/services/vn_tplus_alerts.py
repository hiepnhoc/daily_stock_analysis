# -*- coding: utf-8 -*-
"""Deterministic VN T+ intraday alert evaluation using DNSE read-only data."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence

VN_TPLUS_ALERT_TYPES = frozenset({"vn_tplus_setup"})
_DEFAULT_SIGNALS = ("stop", "target", "fomo_rr", "breakout", "buy_zone", "volume_spike")
_ALLOWED_SIGNALS = frozenset(_DEFAULT_SIGNALS)


@dataclass(frozen=True)
class VNTPlusSetupAlert:
    stock_code: str
    parameters: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    alert_type: str = "vn_tplus_setup"


@dataclass(frozen=True)
class VNTPlusEvaluation:
    triggered: bool
    signal: str | None
    severity: str
    observed_value: float | None
    threshold: float | None
    message: str
    data_timestamp: datetime | None
    risk_reward: float | None = None
    volume_ratio: float | None = None


def _positive(value: Any, default: float, *, allow_zero: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    minimum = 0.0 if allow_zero else 1e-12
    if number < minimum:
        raise ValueError("numeric alert parameter is outside the allowed range")
    return number


def normalize_vn_tplus_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(parameters, Mapping):
        raise ValueError("parameters must be an object")
    raw_signals = parameters.get("signals", _DEFAULT_SIGNALS)
    if isinstance(raw_signals, str):
        raw_signals = [part.strip() for part in raw_signals.split(",") if part.strip()]
    if not isinstance(raw_signals, Sequence) or isinstance(raw_signals, (bytes, bytearray)):
        raise ValueError("signals must be an array")
    signals: list[str] = []
    for item in raw_signals:
        signal = str(item).strip().lower()
        if signal not in _ALLOWED_SIGNALS:
            raise ValueError(f"unsupported VN T+ signal: {signal or '<empty>'}")
        if signal not in signals:
            signals.append(signal)
    if not signals:
        raise ValueError("signals must not be empty")
    return {
        "signals": signals,
        "min_rr": _positive(parameters.get("min_rr"), 1.2),
        "volume_ratio": _positive(parameters.get("volume_ratio"), 1.0),
        "breakout_volume_ratio": _positive(parameters.get("breakout_volume_ratio"), 0.5, allow_zero=True),
        "near_pct": _positive(parameters.get("near_pct"), 0.0, allow_zero=True),
    }


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _mapping(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return dict(value) if isinstance(value, Mapping) else {}


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _risk_reward(price: float, stop: float | None, target: float | None) -> float | None:
    if stop is None or target is None or price <= stop:
        return None
    risk = price - stop
    return (target - price) / risk if risk > 0 else None


def evaluate_vn_tplus_setup(
    rule: VNTPlusSetupAlert,
    *,
    plan: Mapping[str, Any] | Any,
    quote: Mapping[str, Any] | Any,
) -> VNTPlusEvaluation:
    plan_data = _mapping(plan)
    quote_data = _mapping(quote)
    params = normalize_vn_tplus_parameters(rule.parameters)
    signals = set(params["signals"])
    symbol = str(rule.stock_code or plan_data.get("ticker") or quote_data.get("symbol") or "").upper()
    price = _number(quote_data.get("price"))
    timestamp = _timestamp(quote_data.get("time") or quote_data.get("timestamp"))
    if price is None or price <= 0:
        return VNTPlusEvaluation(False, None, "info", None, None, f"{symbol}: DNSE chưa có giá live hợp lệ", timestamp)

    buy_zone = plan_data.get("buyZone") or []
    buy_low = _number(buy_zone[0]) if isinstance(buy_zone, (list, tuple)) and len(buy_zone) >= 2 else None
    buy_high = _number(buy_zone[1]) if isinstance(buy_zone, (list, tuple)) and len(buy_zone) >= 2 else None
    breakout = _number(plan_data.get("breakoutTrigger"))
    stop = _number(plan_data.get("stopLoss"))
    raw_targets = plan_data.get("targets")
    targets = raw_targets if isinstance(raw_targets, list) else []
    target1 = _number(targets[0]) if targets else None
    target2 = _number(targets[1]) if len(targets) > 1 else None
    technical = _mapping(plan_data.get("technical"))
    vol20 = _number(technical.get("vol20"))
    live_volume = _number(quote_data.get("totalVolumeShares"))
    volume_ratio = live_volume / vol20 if live_volume is not None and vol20 and vol20 > 0 else None
    rr = _risk_reward(price, stop, target1)
    near_factor = params["near_pct"] / 100.0

    if "stop" in signals and stop is not None and price <= stop * (1 + near_factor):
        return VNTPlusEvaluation(True, "stop", "critical", price, stop, f"{symbol} {price:.2f}: sát/thủng stop {stop:.2f}; ưu tiên bảo toàn vốn, không bình quân giá xuống", timestamp, rr, volume_ratio)
    if "target" in signals and target2 is not None and price >= target2:
        return VNTPlusEvaluation(True, "target2", "warning", price, target2, f"{symbol} {price:.2f}: chạm/vượt T2 {target2:.2f}; cân nhắc chốt phần còn lại theo thanh khoản", timestamp, rr, volume_ratio)
    if "target" in signals and target1 is not None and price >= target1:
        return VNTPlusEvaluation(True, "target1", "warning", price, target1, f"{symbol} {price:.2f}: chạm/vượt T1 {target1:.2f}; cân nhắc chốt một phần", timestamp, rr, volume_ratio)
    if "fomo_rr" in signals and buy_high is not None and price > buy_high and rr is not None and rr < params["min_rr"]:
        return VNTPlusEvaluation(True, "fomo_rr", "warning", price, params["min_rr"], f"{symbol} {price:.2f}: đã vượt buy_high {buy_high:.2f}, R:R T1 còn {rr:.2f} < {params['min_rr']:.2f}; không mua đuổi", timestamp, rr, volume_ratio)
    if "breakout" in signals and breakout is not None and price >= breakout:
        volume_ok = volume_ratio is not None and volume_ratio >= params["breakout_volume_ratio"]
        if volume_ok:
            return VNTPlusEvaluation(True, "breakout", "warning", price, breakout, f"{symbol} {price:.2f}: vượt breakout {breakout:.2f}, volume/Vol20={volume_ratio:.2f}; chờ giữ giá, không đuổi nếu R:R xấu", timestamp, rr, volume_ratio)
    if "buy_zone" in signals and buy_low is not None and buy_high is not None and buy_low <= price <= buy_high:
        rr_text = f", R:R T1={rr:.2f}" if rr is not None else ""
        return VNTPlusEvaluation(True, "buy_zone", "info", price, buy_high, f"{symbol} {price:.2f}: vào vùng mua {buy_low:.2f}–{buy_high:.2f}{rr_text}; chỉ giải ngân theo size plan", timestamp, rr, volume_ratio)
    if "volume_spike" in signals and volume_ratio is not None and volume_ratio >= params["volume_ratio"]:
        return VNTPlusEvaluation(True, "volume_spike", "info", volume_ratio, params["volume_ratio"], f"{symbol}: volume/Vol20={volume_ratio:.2f}x; kiểm tra hướng giá và cung/cầu trước khi hành động", timestamp, rr, volume_ratio)

    details = [f"giá {price:.2f}"]
    if rr is not None:
        details.append(f"R:R T1 {rr:.2f}")
    if volume_ratio is not None:
        details.append(f"volume/Vol20 {volume_ratio:.2f}x")
    return VNTPlusEvaluation(False, None, "info", price, None, f"{symbol}: chưa có trigger T+ ({', '.join(details)})", timestamp, rr, volume_ratio)


def evaluate_vn_tplus_live(rule: VNTPlusSetupAlert) -> VNTPlusEvaluation:
    from src.vn.data import dnse_openapi
    from src.vn.services import vn_market_service

    plan = vn_market_service.analyze_ticker(rule.stock_code, include_news=False)
    quote = dnse_openapi.fetch_latest_trade(rule.stock_code)
    return evaluate_vn_tplus_setup(rule, plan=plan, quote=quote)


def bootstrap_vn_tplus_rules(
    watchlist: Sequence[str],
    *,
    service: Any = None,
    cooldown_seconds: int = 900,
) -> dict[str, Any]:
    """Idempotently create persisted DNSE VN T+ rules for a watchlist."""
    if service is None:
        from src.services.alert_service import AlertService

        service = AlertService()
    symbols: list[str] = []
    for raw_symbol in watchlist:
        symbol = str(raw_symbol or "").upper().strip()
        if symbol and symbol.isalnum() and len(symbol) <= 10 and symbol not in symbols:
            symbols.append(symbol)
    existing = service.list_rules(alert_type="vn_tplus_setup", page=1, page_size=1000).get("items", [])
    existing_by_symbol = {
        str(item.get("target") or "").upper(): item
        for item in existing
        if item.get("target_scope") == "single_symbol"
    }
    items: list[dict[str, Any]] = []
    created = 0
    for symbol in symbols:
        row = existing_by_symbol.get(symbol)
        if row is None:
            row = service.create_rule(
                {
                    "name": f"VN T+ {symbol} · DNSE",
                    "target_scope": "single_symbol",
                    "target": symbol,
                    "alert_type": "vn_tplus_setup",
                    "parameters": {},
                    "severity": "warning",
                    "enabled": True,
                    "cooldown_policy": {"cooldown_seconds": max(0, int(cooldown_seconds))},
                }
            )
            created += 1
        items.append(row)
    return {"items": items, "created": created, "reused": len(items) - created}


def check_vn_tplus_watchlist(watchlist: Sequence[str]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for raw_symbol in watchlist:
        symbol = str(raw_symbol or "").upper().strip()
        if not symbol:
            continue
        rule = VNTPlusSetupAlert(stock_code=symbol, parameters=normalize_vn_tplus_parameters({}))
        evaluation = evaluate_vn_tplus_live(rule)
        items.append(
            {
                "ticker": symbol,
                "triggered": evaluation.triggered,
                "signal": evaluation.signal,
                "severity": evaluation.severity,
                "observedValue": evaluation.observed_value,
                "threshold": evaluation.threshold,
                "riskReward": round(evaluation.risk_reward, 4) if evaluation.risk_reward is not None else None,
                "volumeRatio": round(evaluation.volume_ratio, 4) if evaluation.volume_ratio is not None else None,
                "dataTimestamp": evaluation.data_timestamp.isoformat() if evaluation.data_timestamp else None,
                "message": evaluation.message,
                "source": "dnse_openapi",
            }
        )
    items.sort(key=lambda item: (not item["triggered"], item["ticker"]))
    return {"items": items}
