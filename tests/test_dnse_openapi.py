# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import Mock

import pandas as pd

from src.vn.data import dnse_openapi, provider


class _Response:
    def __init__(self, payload, *, status_code: int = 200, headers: dict | None = None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = str(payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _set_dnse_env(monkeypatch) -> None:
    monkeypatch.setenv("DNSE_API_KEY", "dnse-key")
    monkeypatch.setenv("DNSE_API_SECRET", "dnse-secret")
    monkeypatch.setenv("DNSE_BASE_URL", "https://openapi.dnse.com.vn")


def test_dnse_status_is_secret_safe(monkeypatch) -> None:
    _set_dnse_env(monkeypatch)

    status = dnse_openapi.get_status()

    assert status == {
        "provider": "dnse_openapi",
        "configured": True,
        "mode": "market_data_read_only",
        "apiUrl": "https://openapi.dnse.com.vn",
        "priceUnit": "thousand_vnd",
        "restOhlc": True,
        "websocket": True,
        "websocketTransport": "native_protocol",
    }
    serialized = str(status).lower()
    assert "dnse-key" not in serialized
    assert "dnse-secret" not in serialized


def test_dnse_websocket_contract_uses_string_nonce_and_subscribe_envelope(monkeypatch) -> None:
    _set_dnse_env(monkeypatch)
    credentials = dnse_openapi._credentials()

    auth = dnse_openapi._websocket_auth_message(
        credentials,
        timestamp=1_750_000_000,
        nonce="1750000000123456",
    )
    subscribe = dnse_openapi._websocket_subscribe_message("hpg")

    assert auth["action"] == "auth"
    assert auth["timestamp"] == 1_750_000_000
    assert auth["nonce"] == "1750000000123456"
    assert isinstance(auth["nonce"], str)
    assert len(auth["signature"]) == 64
    assert subscribe == {
        "action": "subscribe",
        "channels": [
            {"name": "tick.G1.json", "symbols": ["HPG"]},
            {"name": "top_price.G1.json", "symbols": ["HPG"]},
            {"name": "ohlc.1.json", "symbols": ["HPG"]},
        ],
    }


def test_dnse_fetch_daily_bars_signs_request_and_normalizes_parallel_arrays(monkeypatch) -> None:
    _set_dnse_env(monkeypatch)
    session = Mock()
    session.get.return_value = _Response(
        {
            "t": [1784851200, 1784937600],
            "o": [27.0, 27.5],
            "h": [28.0, 28.5],
            "l": [26.5, 27.0],
            "c": [27.5, 28.0],
            "v": [1_000_000, 1_200_000],
            "nextTime": 0,
        },
        headers={
            "X-Ratelimit-Limit": "100",
            "X-Ratelimit-Remaining": "98",
            "X-Ratelimit-Reset": "1785000000",
        },
    )

    frame = dnse_openapi.fetch_daily_bars("hpg", days=2, session=session)

    assert list(frame.columns) == ["date", "open", "high", "low", "close", "volume", "value"]
    assert frame["close"].tolist() == [27.5, 28.0]
    assert frame["volume"].tolist() == [1_000_000, 1_200_000]
    assert frame.attrs["source"] == "dnse_openapi"
    assert frame.attrs["price_unit"] == "thousand_vnd"
    assert frame.attrs["rate_limit"] == {"limit": "100", "remaining": "98", "reset": "1785000000"}

    call = session.get.call_args
    assert call.args[0] == "https://openapi.dnse.com.vn/price/ohlc"
    assert call.kwargs["params"]["symbol"] == "HPG"
    assert call.kwargs["params"]["type"] == "STOCK"
    assert call.kwargs["params"]["resolution"] == "1D"
    headers = {key.lower(): value for key, value in call.kwargs["headers"].items()}
    assert headers["x-api-key"] == "dnse-key"
    assert "x-aux-date" in headers
    assert 'keyId="dnse-key"' in headers["x-signature"]
    assert 'algorithm="hmac-sha256"' in headers["x-signature"]


def test_dnse_ohlc_uses_index_market_type_for_vn_indices(monkeypatch) -> None:
    _set_dnse_env(monkeypatch)
    session = Mock()
    session.get.return_value = _Response({"t": [], "o": [], "h": [], "l": [], "c": [], "v": [], "nextTime": 0})

    dnse_openapi.fetch_daily_bars("VN30", days=5, session=session)

    assert session.get.call_args.kwargs["params"]["type"] == "INDEX"


def test_dnse_fetch_latest_trade_normalizes_market_snapshot(monkeypatch) -> None:
    _set_dnse_env(monkeypatch)
    session = Mock()
    session.get.return_value = _Response(
        {
            "trades": [
                {
                    "symbol": "HPG",
                    "matchPrice": 27.5,
                    "matchQtty": 500,
                    "side": "B",
                    "avgPrice": 27.4,
                    "totalVolumeTraded": 1_200_000,
                    "grossTradeAmount": 32.88,
                    "highestPrice": 28.0,
                    "lowestPrice": 26.8,
                    "openPrice": 27.0,
                    "time": "10:15:00",
                }
            ]
        }
    )

    snapshot = dnse_openapi.fetch_latest_trade("HPG", session=session)

    assert snapshot == {
        "symbol": "HPG",
        "price": 27.5,
        "matchVolume": 500,
        "side": "B",
        "avgPrice": 27.4,
        "totalVolumeRaw": 1_200_000,
        "totalVolumeShares": 12_000_000,
        "grossTradeAmountBillionVnd": 32.88,
        "totalValueVnd": 32_880_000_000.0,
        "high": 28.0,
        "low": 26.8,
        "open": 27.0,
        "time": "10:15:00",
        "source": "dnse_openapi",
    }
    assert session.get.call_args.args[0] == "https://openapi.dnse.com.vn/price/HPG/trades/latest"
    assert session.get.call_args.kwargs["params"] == {"boardId": "G1"}


def test_provider_auto_prefers_dnse_then_ssi_then_vndirect(monkeypatch) -> None:
    _set_dnse_env(monkeypatch)
    monkeypatch.setenv("SSI_FASTCONNECT_API_KEY", "ssi-key")
    monkeypatch.setenv("SSI_FASTCONNECT_API_SECRET", "ssi-secret")
    monkeypatch.setenv("VN_MARKET_DATA_PROVIDER", "auto")

    dnse_frame = pd.DataFrame(
        [{"date": "2026-07-25", "open": 27.5, "high": 28.5, "low": 27.0, "close": 28.0, "volume": 1_200_000, "value": None}]
    )
    dnse_frame.attrs["source"] = "dnse_openapi"
    dnse_fetch = Mock(return_value=dnse_frame)
    ssi_fetch = Mock(return_value=pd.DataFrame())
    vndirect_fetch = Mock(return_value=pd.DataFrame())
    monkeypatch.setattr(provider.dnse_openapi, "fetch_daily_bars", dnse_fetch)
    monkeypatch.setattr(provider.ssi_fastconnect, "fetch_daily_bars", ssi_fetch)
    monkeypatch.setattr(provider.vndirect, "fetch_ohlcv", vndirect_fetch)

    result = provider.get_daily_bars("HPG", days=260)

    assert result.attrs["source"] == "dnse_openapi"
    ssi_fetch.assert_not_called()
    vndirect_fetch.assert_not_called()

    dnse_fetch.return_value = pd.DataFrame()
    ssi_frame = dnse_frame.copy()
    ssi_frame.attrs["source"] = "ssi_fastconnect_v3"
    ssi_fetch.return_value = ssi_frame

    result = provider.get_daily_bars("HPG", days=260)

    assert result.attrs["source"] == "ssi_fastconnect_v3"
    assert result.attrs["fallback_from"] == "dnse_openapi"
    vndirect_fetch.assert_not_called()

    ssi_fetch.return_value = pd.DataFrame()
    fallback = dnse_frame.copy()
    vndirect_fetch.return_value = fallback

    result = provider.get_daily_bars("HPG", days=260)

    assert result.attrs["source"] == "vndirect"
    assert result.attrs["fallback_from"] == "dnse_openapi,ssi_fastconnect_v3"


def test_provider_status_reports_dnse_primary_without_secrets(monkeypatch) -> None:
    _set_dnse_env(monkeypatch)
    monkeypatch.setenv("SSI_FASTCONNECT_API_KEY", "ssi-key")
    monkeypatch.setenv("SSI_FASTCONNECT_API_SECRET", "ssi-secret")
    monkeypatch.setenv("VN_MARKET_DATA_PROVIDER", "auto")

    status = provider.get_provider_status()

    assert status["configuredProvider"] == "auto"
    assert status["effectivePrimary"] == "dnse_openapi"
    assert status["fallbackChain"] == ["ssi_fastconnect_v3", "vndirect"]
    assert status["dnseOpenAPI"]["configured"] is True
    assert status["executionEnabled"] is False
    serialized = str(status).lower()
    assert "dnse-key" not in serialized
    assert "dnse-secret" not in serialized
    assert "ssi-key" not in serialized
    assert "ssi-secret" not in serialized
