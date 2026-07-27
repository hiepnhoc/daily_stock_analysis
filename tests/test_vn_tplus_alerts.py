# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.services.vn_tplus_alerts import (
    VNTPlusSetupAlert,
    bootstrap_vn_tplus_rules,
    evaluate_vn_tplus_setup,
    normalize_vn_tplus_parameters,
)


def _plan(**overrides):
    data = {
        "ticker": "HPG",
        "action": "buy_zone",
        "score": 72,
        "buyZone": [20.4, 20.8],
        "breakoutTrigger": 21.2,
        "stopLoss": 19.8,
        "targets": [22.0, 23.0],
        "technical": {"vol20": 4_000_000},
    }
    data.update(overrides)
    return data


def _quote(**overrides):
    data = {
        "symbol": "HPG",
        "price": 20.6,
        "totalVolumeShares": 2_000_000,
        "time": "2026-07-27 10:30:00.000",
        "source": "dnse_openapi",
    }
    data.update(overrides)
    return data


def test_normalize_vn_tplus_parameters_has_risk_first_defaults() -> None:
    params = normalize_vn_tplus_parameters({})
    assert params == {
        "signals": ["stop", "target", "fomo_rr", "breakout", "buy_zone", "volume_spike"],
        "min_rr": 1.2,
        "volume_ratio": 1.0,
        "breakout_volume_ratio": 0.5,
        "near_pct": 0.0,
    }


def test_evaluator_prioritizes_stop_over_other_signals() -> None:
    result = evaluate_vn_tplus_setup(
        VNTPlusSetupAlert(stock_code="HPG", parameters=normalize_vn_tplus_parameters({})),
        plan=_plan(),
        quote=_quote(price=19.75, totalVolumeShares=5_000_000),
    )
    assert result.triggered
    assert result.signal == "stop"
    assert result.severity == "critical"
    assert result.observed_value == 19.75
    assert result.threshold == 19.8


def test_evaluator_triggers_buy_zone_with_inspectable_rr() -> None:
    result = evaluate_vn_tplus_setup(
        VNTPlusSetupAlert(stock_code="HPG", parameters=normalize_vn_tplus_parameters({})),
        plan=_plan(),
        quote=_quote(price=20.6),
    )
    assert result.triggered
    assert result.signal == "buy_zone"
    assert result.risk_reward == pytest.approx((22.0 - 20.6) / (20.6 - 19.8))
    assert "vùng mua" in result.message


def test_evaluator_emits_anti_fomo_when_current_rr_is_below_gate() -> None:
    result = evaluate_vn_tplus_setup(
        VNTPlusSetupAlert(stock_code="HPG", parameters=normalize_vn_tplus_parameters({"signals": ["fomo_rr"]})),
        plan=_plan(),
        quote=_quote(price=21.5),
    )
    assert result.triggered
    assert result.signal == "fomo_rr"
    assert result.risk_reward == pytest.approx((22.0 - 21.5) / (21.5 - 19.8))
    assert result.risk_reward < 1.2
    assert "không mua đuổi" in result.message.lower()


def test_breakout_requires_configured_live_volume_confirmation() -> None:
    rule = VNTPlusSetupAlert(
        stock_code="HPG",
        parameters=normalize_vn_tplus_parameters({"signals": ["breakout"], "breakout_volume_ratio": 0.5}),
    )
    weak = evaluate_vn_tplus_setup(rule, plan=_plan(), quote=_quote(price=21.25, totalVolumeShares=1_500_000))
    strong = evaluate_vn_tplus_setup(rule, plan=_plan(), quote=_quote(price=21.25, totalVolumeShares=2_100_000))
    assert not weak.triggered
    assert strong.triggered
    assert strong.signal == "breakout"
    assert strong.volume_ratio == pytest.approx(0.525)


def test_alert_service_accepts_vn_tplus_runtime_rule(monkeypatch) -> None:
    from src.services.alert_service import AlertService

    service = AlertService.__new__(AlertService)
    normalized = service._normalize_parameters("vn_tplus_setup", {})
    assert normalized["min_rr"] == 1.2

    row = SimpleNamespace(
        id=7,
        name="HPG T+",
        target_scope="single_symbol",
        target="HPG",
        alert_type="vn_tplus_setup",
        parameters='{"signals":["stop","buy_zone"],"min_rr":1.2,"volume_ratio":1.0,"breakout_volume_ratio":0.5,"near_pct":0.0}',
        severity="warning",
        enabled=True,
        source="api",
        cooldown_policy=None,
        notification_policy=None,
        created_at=None,
        updated_at=None,
    )
    runtime = service._to_runtime_rule(row)
    assert isinstance(runtime, VNTPlusSetupAlert)
    assert runtime.stock_code == "HPG"
    assert runtime.metadata["persisted_rule_id"] == 7


def test_bootstrap_rules_is_idempotent_and_sets_15_minute_cooldown() -> None:
    class FakeService:
        def __init__(self):
            self.rows = []

        def list_rules(self, **_kwargs):
            return {"items": list(self.rows)}

        def create_rule(self, payload):
            row = {
                "id": len(self.rows) + 1,
                "target_scope": payload["target_scope"],
                "target": payload["target"],
                "alert_type": payload["alert_type"],
                "cooldown_policy": payload["cooldown_policy"],
            }
            self.rows.append(row)
            return row

    service = FakeService()
    first = bootstrap_vn_tplus_rules(["hpg", "FPT", "HPG"], service=service)
    second = bootstrap_vn_tplus_rules(["HPG", "FPT"], service=service)
    assert first["created"] == 2
    assert first["reused"] == 0
    assert second["created"] == 0
    assert second["reused"] == 2
    assert all(item["cooldown_policy"] == {"cooldown_seconds": 900} for item in first["items"])
