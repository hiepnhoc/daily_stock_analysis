# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from api.app import create_app


def _sample_ohlcv(rows: int = 260) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=rows, freq="B")
    close = pd.Series([20 + i * 0.04 for i in range(rows)], dtype="float64")
    return pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.1,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": [1_000_000 + i * 1_000 for i in range(rows)],
        }
    )


def test_vn_indicators_latest_snapshot_contains_tplus_stack() -> None:
    from src.vn.indicators.technicals import add_indicators, latest_technical_snapshot

    enriched = add_indicators(_sample_ohlcv())
    snapshot = latest_technical_snapshot(enriched)

    for key in ("ema20", "ema60", "ma50", "ma200", "rsi14", "macd", "macdSignal", "macdHist", "vol20", "atr14"):
        assert key in snapshot
        assert snapshot[key] is not None
    assert snapshot["close"] > snapshot["ema20"] > snapshot["ema60"]


def test_bearish_market_downgrades_vn_action_plan() -> None:
    from src.vn.analysis.action_plan import build_action_plan
    from src.vn.schemas import TechnicalSnapshot, VNMarketContext

    technical = TechnicalSnapshot(
        close=30,
        ema20=28,
        ema60=26,
        ma50=27,
        ma200=22,
        rsi14=62,
        macd=0.5,
        macdSignal=0.3,
        macdHist=0.2,
        volume=2_000_000,
        vol20=1_000_000,
        volumeRatio=2.0,
        atr14=0.8,
    )
    market = VNMarketContext(marketBias="bearish", warnings=["VNINDEX dưới EMA20"])

    plan = build_action_plan("HPG", technical, market)

    assert plan.action in {"watch", "avoid"}
    assert plan.positionSizePct <= 15
    assert any("VNINDEX" in flag or "thị trường" in flag.lower() for flag in plan.riskFlags)


def test_vn_scan_api_returns_action_plans(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    with patch("src.vn.data.provider.get_daily_bars", return_value=_sample_ohlcv()):
        client = TestClient(create_app(static_dir=static_dir))
        response = client.post("/api/v1/vn/scan", json={"watchlist": ["HPG", "FPT"], "mode": "tplus"})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["ticker"] for item in payload["items"]] == ["HPG", "FPT"]
    for item in payload["items"]:
        assert item["score"] > 0
        assert item["stopLoss"] is not None
        assert item["targets"]
        assert "chưa kiểm chứng news/catalyst" in item["riskFlags"]


def test_vn_report_exports_to_shared_hermes_knowledge(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    with patch("src.vn.data.provider.get_daily_bars", return_value=_sample_ohlcv()):
        client = TestClient(create_app(static_dir=static_dir))
        response = client.post("/api/v1/vn/report", json={"watchlist": ["HPG"], "mode": "tplus"})

    assert response.status_code == 200, response.text
    payload = response.json()
    for key in ("htmlPath", "jsonPath"):
        path = Path(payload[key])
        assert path.exists()
        assert path.stat().st_size > 0
        assert "/hermes-agent/knowledge/stock-reports/vn-market/" in str(path)


def test_market_overview_uses_ssi_breadth_when_available(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    breadth = {"advancers": 100, "decliners": 50, "ceiling": 5, "floor": 2, "unchanged": 20, "totalValue": 123456789}

    with patch("src.vn.data.provider.get_daily_bars", return_value=_sample_ohlcv()), \
         patch("src.vn.data.ssi_iboard.fetch_exchange_breadth", return_value=breadth):
        client = TestClient(create_app(static_dir=static_dir))
        response = client.get("/api/v1/vn/market-overview")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["breadth"]["advancers"] == 100
    assert payload["breadth"]["decliners"] == 50
    assert payload["liquidity"]["totalValue"] == 123456789


def test_analyze_endpoint_returns_technical_snapshot(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    with patch("src.vn.data.provider.get_daily_bars", return_value=_sample_ohlcv()):
        client = TestClient(create_app(static_dir=static_dir))
        response = client.get("/api/v1/vn/analyze/HPG")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ticker"] == "HPG"
    assert payload["technical"]["ema20"] is not None
    assert payload["breakoutTrigger"] is not None
    assert payload["riskFlags"]


def test_portfolio_tplus_endpoint_splits_sellable_pending_and_pl(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    with patch("src.vn.data.provider.get_daily_bars", return_value=_sample_ohlcv()), \
         patch("src.vn.data.ssi_iboard.fetch_live_quote", return_value={"price": 31.0, "source": "ssi_iboard"}):
        client = TestClient(create_app(static_dir=static_dir))
        response = client.post(
            "/api/v1/vn/portfolio-check",
            json={
                "holdings": [
                    {"ticker": "HPG", "quantity": 1000, "avgCost": 30.0, "sellableQty": 600, "pendingQty": 400}
                ]
            },
        )

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["ticker"] == "HPG"
    assert item["currentPrice"] == 31.0
    assert item["plPct"] > 3
    assert item["sellableQty"] == 600
    assert item["pendingQty"] == 400
    assert item["todayPlan"]
    assert "hàng về" in item["pendingPlan"]
