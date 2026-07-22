# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import Mock

from src.vn.data import ssi_iboard


def test_live_quote_opens_short_circuit_after_source_failure(monkeypatch) -> None:
    request = Mock(side_effect=TimeoutError("SSI timeout"))
    monkeypatch.setattr(ssi_iboard.requests, "get", request)
    monkeypatch.setattr(ssi_iboard, "_failure_until", 0.0)

    assert ssi_iboard.fetch_live_quote("BID", timeout=0.1) == {}
    assert ssi_iboard.fetch_live_quote("CTG", timeout=0.1) == {}

    request.assert_called_once()
