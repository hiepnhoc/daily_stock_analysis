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


def test_market_context_does_not_overwrite_bearish_when_close_is_above_ema20_but_below_ema60() -> None:
    from src.vn.services.vn_market_service import build_market_context

    with patch("src.vn.services.vn_market_service.provider.get_daily_bars", return_value=_sample_ohlcv()), \
         patch(
             "src.vn.services.vn_market_service.latest_technical_snapshot",
             return_value={"close": 95.0, "ema20": 90.0, "ema60": 100.0, "rsi14": 55.0},
         ):
        market = build_market_context()

    assert market.marketBias == "bearish"
    assert any("EMA60" in warning for warning in market.warnings)


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


def test_vn_readiness_endpoint_is_lightweight(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    client = TestClient(create_app(static_dir=static_dir))
    response = client.get("/api/v1/vn/readiness")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "vn-market"}


def test_vn_provider_status_endpoint_is_secret_safe(tmp_path: Path, monkeypatch) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.delenv("DNSE_API_KEY", raising=False)
    monkeypatch.delenv("DNSE_API_SECRET", raising=False)
    monkeypatch.setenv("SSI_FASTCONNECT_CLIENT_ID", "client-id")
    monkeypatch.setenv("SSI_FASTCONNECT_API_KEY", "api-key")
    monkeypatch.setenv("SSI_FASTCONNECT_API_SECRET", "api-secret")

    client = TestClient(create_app(static_dir=static_dir))
    response = client.get("/api/v1/vn/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["effectivePrimary"] == "ssi_fastconnect_v3"
    assert payload["executionEnabled"] is False
    serialized = response.text.lower()
    assert "api-key" not in serialized
    assert "api-secret" not in serialized
    assert "client-id" not in serialized


def test_vn_intraday_watch_bootstrap_endpoint_is_idempotent_contract(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    with patch(
        "api.v1.endpoints.vn_market.bootstrap_vn_tplus_rules",
        return_value={"created": 1, "reused": 1, "items": [{"id": 7, "target": "HPG"}, {"id": 8, "target": "FPT"}]},
    ) as bootstrap:
        client = TestClient(create_app(static_dir=static_dir))
        response = client.post(
            "/api/v1/vn/intraday-watch/bootstrap",
            json={"watchlist": ["hpg", "FPT", "HPG"], "cooldownSeconds": 900},
        )

    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1
    bootstrap.assert_called_once_with(["HPG", "FPT"], cooldown_seconds=900)


def test_vn_intraday_watch_rejects_invalid_ticker(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    client = TestClient(create_app(static_dir=static_dir))
    response = client.post("/api/v1/vn/intraday-watch/check", json={"watchlist": ["HPG1"]})
    assert response.status_code == 422


def test_analyze_endpoint_returns_technical_snapshot(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    from src.vn.schemas import DataQuality, NewsCatalyst, NewsItem

    news = NewsCatalyst(
        checked=True,
        source="agent-reach:jina-reader",
        freshnessWindow="7d",
        sentiment="mixed",
        catalysts=[NewsItem(title="HPG có tin public web cần theo dõi", source="CafeF", impact="medium")],
        dataQuality=DataQuality(status="available", source="agent-reach:jina-reader"),
    )
    with patch("src.vn.data.provider.get_daily_bars", return_value=_sample_ohlcv()), \
         patch("src.vn.services.vn_market_service.fetch_news_catalyst", return_value=news):
        client = TestClient(create_app(static_dir=static_dir))
        response = client.get("/api/v1/vn/analyze/HPG")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ticker"] == "HPG"
    assert payload["technical"]["ema20"] is not None
    assert payload["breakoutTrigger"] is not None
    assert payload["riskFlags"]
    assert payload["newsCatalyst"]["checked"] is True
    assert payload["newsCatalyst"]["catalysts"][0]["source"] == "CafeF"
    assert "chưa kiểm chứng news/catalyst" not in payload["riskFlags"]


def test_chart_endpoint_returns_ohlcv_and_moving_averages(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    with patch("src.vn.data.provider.get_daily_bars", return_value=_sample_ohlcv()):
        client = TestClient(create_app(static_dir=static_dir))
        response = client.get("/api/v1/vn/chart/HPG?days=80")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ticker"] == "HPG"
    assert len(payload["items"]) == 80
    latest = payload["items"][-1]
    for key in ("date", "open", "high", "low", "close", "volume", "ema20", "ema60", "ma50", "rsi14", "macd", "macdSignal", "macdHist"):
        assert latest[key] is not None


def test_portfolio_tplus_endpoint_splits_sellable_pending_and_pl(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    with patch("src.vn.data.provider.get_daily_bars", return_value=_sample_ohlcv()), \
         patch("src.vn.data.ssi_iboard.fetch_live_quote", return_value={"price": 31000.0, "source": "ssi_iboard"}):
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


def test_portfolio_tplus_can_include_agent_reach_news(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    from src.vn.schemas import DataQuality, NewsCatalyst, NewsItem

    news = NewsCatalyst(
        checked=True,
        source="agent-reach:multi-source",
        freshnessWindow="7d",
        sentiment="positive",
        catalysts=[
            NewsItem(
                title="HPG công bố thông tin mới",
                source="CafeF",
                url="https://example.com/hpg",
                impact="medium",
            )
        ],
        dataQuality=DataQuality(status="available", source="agent-reach:multi-source"),
    )
    with patch("src.vn.data.provider.get_daily_bars", return_value=_sample_ohlcv()), \
         patch("src.vn.data.ssi_iboard.fetch_live_quote", return_value={"price": 31000.0, "source": "ssi_iboard"}), \
         patch("src.vn.services.vn_market_service.fetch_news_catalyst", return_value=news):
        client = TestClient(create_app(static_dir=static_dir))
        response = client.post(
            "/api/v1/vn/portfolio-check",
            json={
                "includeNews": True,
                "holdings": [
                    {"ticker": "HPG", "quantity": 1000, "avgCost": 30.0, "sellableQty": 600, "pendingQty": 400}
                ],
            },
        )

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["newsCatalyst"]["checked"] is True
    assert item["newsCatalyst"]["catalysts"][0]["url"] == "https://example.com/hpg"


def test_portfolio_endpoint_rejects_invalid_holdings_before_service_call(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    client = TestClient(create_app(static_dir=static_dir))

    invalid_holdings = [
        {"ticker": "???", "quantity": 100, "avgCost": 30, "sellableQty": 100, "pendingQty": 0},
        {"ticker": "HPG", "quantity": 0, "avgCost": 30, "sellableQty": 0, "pendingQty": 0},
        {"ticker": "FPT", "quantity": 100, "avgCost": -1, "sellableQty": 100, "pendingQty": 0},
        {"ticker": "SSI", "quantity": 100, "avgCost": 25, "sellableQty": 80, "pendingQty": 30},
    ]

    for holding in invalid_holdings:
        response = client.post("/api/v1/vn/portfolio-check", json={"holdings": [holding]})
        assert response.status_code == 422, response.text


def test_sector_flow_groups_watchlist_by_sector(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    with patch("src.vn.data.provider.get_daily_bars", return_value=_sample_ohlcv()):
        client = TestClient(create_app(static_dir=static_dir))
        response = client.post("/api/v1/vn/sector-flow", json={"watchlist": ["HPG", "HSG", "FPT"], "mode": "tplus"})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["items"]
    assert any(item["sector"] in {"Thép", "Công nghệ"} for item in payload["items"])
    assert payload["items"][0]["tickers"]


def test_alerts_check_flags_stop_breakout_and_hot_rsi(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    with patch("src.vn.data.provider.get_daily_bars", return_value=_sample_ohlcv()):
        client = TestClient(create_app(static_dir=static_dir))
        response = client.post("/api/v1/vn/alerts/check", json={"watchlist": ["HPG"], "mode": "tplus"})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["items"]
    assert payload["items"][0]["ticker"] == "HPG"
    assert payload["items"][0]["alerts"]


def test_alert_rules_check_evaluates_custom_thresholds(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    with patch("src.vn.data.provider.get_daily_bars", return_value=_sample_ohlcv()):
        client = TestClient(create_app(static_dir=static_dir))
        response = client.post(
            "/api/v1/vn/alerts/rules/check",
            json={"rules": [{"id": "r1", "ticker": "HPG", "condition": "price_above", "threshold": 20, "enabled": True}]},
        )

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["ticker"] == "HPG"
    assert item["triggered"] is True
    assert "TRIGGER" in item["message"]


def test_daily_playbook_returns_market_setups_and_portfolio_actions(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    with patch("src.vn.data.provider.get_daily_bars", return_value=_sample_ohlcv()), \
         patch("src.vn.data.ssi_iboard.fetch_live_quote", return_value={"price": 31000.0, "source": "ssi_iboard"}):
        client = TestClient(create_app(static_dir=static_dir))
        response = client.post(
            "/api/v1/vn/daily-playbook",
            json={
                "watchlist": ["HPG", "FPT", "SSI"],
                "holdings": [{"ticker": "HPG", "quantity": 1000, "avgCost": 30.0, "sellableQty": 600, "pendingQty": 400}],
                "mode": "tplus",
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"]
    assert all(item["action"] not in {"avoid", "sell_reduce"} for item in payload["topSetups"])
    assert payload["topSetups"] or payload["avoidList"]
    assert payload["sectorBias"]
    assert payload["portfolioActions"][0]["ticker"] == "HPG"
    assert "chưa kiểm chứng news/catalyst" in payload["warnings"]


def test_daily_playbook_does_not_label_avoid_rows_as_top_setups(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    avoid_item = {
        "ticker": "HPG", "action": "avoid", "score": 20, "confidence": 0.2,
        "buyZone": None, "breakoutTrigger": None, "stopLoss": None, "targets": [],
        "positionSizePct": 0, "reasons": [], "riskFlags": ["setup yếu"],
        "dataQuality": {}, "technical": None, "newsCatalyst": None,
    }
    overview = {
        "refDate": "2026-07-10", "indices": [],
        "breadth": {"advancers": 10, "decliners": 20, "ceiling": 0, "floor": 0, "unchanged": 0},
        "liquidity": {"totalValue": None, "vs20dPct": None},
        "marketBias": "cautious", "warnings": [],
    }

    with patch("src.vn.services.vn_market_service.get_market_overview", return_value=overview), \
         patch("src.vn.services.vn_market_service.scan_watchlist", return_value={"items": [avoid_item]}):
        client = TestClient(create_app(static_dir=static_dir))
        response = client.post("/api/v1/vn/daily-playbook", json={"watchlist": ["HPG"], "holdings": [], "mode": "tplus"})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["topSetups"] == []
    assert payload["avoidList"][0]["ticker"] == "HPG"


def test_journal_create_and_list_signal(tmp_path: Path, monkeypatch) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setenv("VN_MARKET_JOURNAL_PATH", str(tmp_path / "journal.jsonl"))

    client = TestClient(create_app(static_dir=static_dir))
    create_resp = client.post(
        "/api/v1/vn/journal",
        json={"ticker": "HPG", "action": "watch", "score": 66, "note": "test signal"},
    )
    assert create_resp.status_code == 200, create_resp.text
    list_resp = client.get("/api/v1/vn/journal")
    assert list_resp.status_code == 200, list_resp.text
    assert list_resp.json()["items"][0]["ticker"] == "HPG"
