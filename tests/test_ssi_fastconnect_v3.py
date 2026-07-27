# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import Mock

import pandas as pd

from src.vn.data import provider, ssi_fastconnect


class _Response:
    def __init__(self, payload, *, status_code: int = 200, headers: dict | None = None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _set_ssi_env(monkeypatch, *, price_unit: str = "thousand_vnd") -> None:
    monkeypatch.delenv("DNSE_API_KEY", raising=False)
    monkeypatch.delenv("DNSE_API_SECRET", raising=False)
    monkeypatch.setenv("SSI_FASTCONNECT_CLIENT_ID", "client-id")
    monkeypatch.setenv("SSI_FASTCONNECT_API_KEY", "api-key")
    monkeypatch.setenv("SSI_FASTCONNECT_API_SECRET", "api-secret")
    monkeypatch.setenv("VN_SSI_PRICE_UNIT", price_unit)


def test_ssi_status_is_secret_safe_when_unconfigured(monkeypatch) -> None:
    for name in (
        "SSI_FASTCONNECT_CLIENT_ID",
        "SSI_FASTCONNECT_API_KEY",
        "SSI_FASTCONNECT_API_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)

    status = ssi_fastconnect.get_status()

    assert status == {
        "provider": "ssi_fastconnect_v3",
        "configured": False,
        "mode": "market_data_read_only",
        "apiUrl": "https://api.ssi.com.vn",
        "priceUnit": "thousand_vnd",
    }
    assert "apiKey" not in status
    assert "apiSecret" not in status
    assert "clientId" not in status


def test_ssi_fetch_daily_bars_authenticates_and_normalizes_vnd_prices(monkeypatch) -> None:
    _set_ssi_env(monkeypatch, price_unit="vnd")
    session = Mock()
    session.post.return_value = _Response({"accessToken": "token-value", "expiresAt": 9999999999})
    session.get.return_value = _Response(
        {
            "data": [
                {
                    "symbol": "HPG",
                    "tradingDate": "2026-07-24",
                    "open": "27000",
                    "high": "28000",
                    "low": "26500",
                    "close": "27500",
                    "volume": "1000000",
                    "value": "27500000000",
                },
                {
                    "symbol": "HPG",
                    "tradingDate": "2026-07-25",
                    "open": "27500",
                    "high": "28500",
                    "low": "27000",
                    "close": "28000",
                    "volume": "1200000",
                    "value": "33600000000",
                },
            ]
        },
        headers={
            "X-RATELIMIT-LIMIT": "100",
            "X-RATELIMIT-REMAINING": "98",
            "X-RATELIMIT-RESET": "1780000000",
        },
    )

    frame = ssi_fastconnect.fetch_daily_bars("hpg", days=2, session=session)

    assert list(frame.columns) == ["date", "open", "high", "low", "close", "volume", "value"]
    assert frame["date"].tolist() == ["2026-07-24", "2026-07-25"]
    assert frame["close"].tolist() == [27.5, 28.0]
    assert frame["volume"].tolist() == [1_000_000, 1_200_000]
    assert frame.attrs["source"] == "ssi_fastconnect_v3"
    assert frame.attrs["price_unit"] == "thousand_vnd"
    assert frame.attrs["rate_limit"] == {"limit": "100", "remaining": "98", "reset": "1780000000"}

    auth_call = session.post.call_args
    assert auth_call.args[0] == "https://api.ssi.com.vn/api/v3/auth/token"
    assert auth_call.kwargs["json"] == {"apiKey": "api-key", "apiSecret": "api-secret"}
    data_call = session.get.call_args
    assert data_call.args[0] == "https://api.ssi.com.vn/api/v3/data/ohlc"
    assert data_call.kwargs["headers"]["Authorization"] == "Bearer token-value"
    assert data_call.kwargs["params"]["timeFrame"] == "1d"


def test_provider_auto_prefers_ssi_then_falls_back_to_vndirect(monkeypatch) -> None:
    _set_ssi_env(monkeypatch)
    monkeypatch.setenv("VN_MARKET_DATA_PROVIDER", "auto")
    ssi_frame = pd.DataFrame(
        [{"date": "2026-07-25", "open": 27.5, "high": 28.5, "low": 27.0, "close": 28.0, "volume": 1_200_000, "value": 33_600_000_000}]
    )
    ssi_frame.attrs["source"] = "ssi_fastconnect_v3"
    monkeypatch.setattr(provider.ssi_fastconnect, "fetch_daily_bars", Mock(return_value=ssi_frame))
    vndirect_fetch = Mock(return_value=pd.DataFrame())
    monkeypatch.setattr(provider.vndirect, "fetch_ohlcv", vndirect_fetch)

    result = provider.get_daily_bars("HPG", days=260)

    assert result.attrs["source"] == "ssi_fastconnect_v3"
    vndirect_fetch.assert_not_called()

    provider.ssi_fastconnect.fetch_daily_bars = Mock(return_value=pd.DataFrame())
    fallback = pd.DataFrame([{"date": "2026-07-25", "open": 27.5, "high": 28.5, "low": 27.0, "close": 28.0, "volume": 1_200_000}])
    vndirect_fetch.return_value = fallback

    result = provider.get_daily_bars("HPG", days=260)

    assert result.attrs["source"] == "vndirect"
    assert result.attrs["fallback_from"] == "ssi_fastconnect_v3"


def test_provider_status_reports_effective_mode_without_secrets(monkeypatch) -> None:
    _set_ssi_env(monkeypatch)
    monkeypatch.setenv("VN_MARKET_DATA_PROVIDER", "auto")

    status = provider.get_provider_status()

    assert status["configuredProvider"] == "auto"
    assert status["effectivePrimary"] == "ssi_fastconnect_v3"
    assert status["fallback"] == "vndirect"
    assert status["ssiFastConnect"]["configured"] is True
    serialized = str(status).lower()
    assert "api-secret" not in serialized
    assert "api-key" not in serialized
    assert "client-id" not in serialized


def test_ssi_fetch_index_summary_normalizes_breadth(monkeypatch) -> None:
    _set_ssi_env(monkeypatch)
    ssi_fastconnect.clear_token_cache()
    session = Mock()
    session.post.return_value = _Response({"data": {"accessToken": "token-value", "expiresAt": 9999999999}})
    session.get.return_value = _Response(
        {
            "data": [
                {
                    "tradingDate": "2026-07-27",
                    "indexValue": "1523.45",
                    "indexChangePercentage": "1.25",
                    "totalAdvanceStock": "210",
                    "totalDeclineStock": "95",
                    "totalNoChangeStock": "42",
                    "totalCeilingStock": "12",
                    "totalFloorStock": "3",
                    "totalMatchValue": "24500000000000",
                }
            ]
        }
    )

    result = ssi_fastconnect.fetch_index_summary("VNINDEX", session=session)

    assert result == {
        "index": "VNINDEX",
        "tradingDate": "2026-07-27",
        "indexValue": 1523.45,
        "changePct": 1.25,
        "advancers": 210,
        "decliners": 95,
        "unchanged": 42,
        "ceiling": 12,
        "floor": 3,
        "totalValue": 24_500_000_000_000.0,
        "source": "ssi_fastconnect_v3",
    }
    assert session.get.call_args.args[0] == "https://api.ssi.com.vn/api/v3/data/indexSummary"
    assert session.get.call_args.kwargs["params"] == {"index": "VNINDEX"}


def test_provider_breadth_uses_fastconnect_then_iboard_fallback(monkeypatch) -> None:
    _set_ssi_env(monkeypatch)
    monkeypatch.setenv("VN_MARKET_DATA_PROVIDER", "auto")
    official = {"advancers": 210, "decliners": 95, "source": "ssi_fastconnect_v3"}
    monkeypatch.setattr(provider.ssi_fastconnect, "fetch_index_summary", Mock(return_value=official))
    iboard_fetch = Mock(return_value={"advancers": 100, "source": "ssi_iboard"})
    monkeypatch.setattr(provider.ssi_iboard, "fetch_exchange_breadth", iboard_fetch)

    assert provider.get_exchange_breadth("hose") == official
    iboard_fetch.assert_not_called()

    provider.ssi_fastconnect.fetch_index_summary = Mock(return_value={})
    fallback = provider.get_exchange_breadth("hose")

    assert fallback["source"] == "ssi_iboard"
    assert fallback["fallback_from"] == "ssi_fastconnect_v3"
