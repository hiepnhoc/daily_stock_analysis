# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import threading

from src.vn.news_catalyst import (
    SourceResult,
    _dedupe_items,
    _decorate_item,
    _public_warning,
    _resolve_tool,
    clear_news_cache,
    fetch_news_catalyst,
)
from src.vn.schemas import NewsItem, NewsSourceStatus


def test_news_item_decorator_classifies_negative_high_impact() -> None:
    item = _decorate_item(
        NewsItem(title="Cổ phiếu PNJ bị bán tháo, giảm sàn sau tin lãnh đạo bị khởi tố", source="Tuổi Trẻ"),
        "agent-reach:rss:google-news",
    )

    assert item.tone == "negative"
    assert item.impact == "high"
    assert item.sourceRoute == "agent-reach:rss:google-news"


def test_news_dedupe_prefers_first_url_or_title() -> None:
    items = _dedupe_items(
        [
            NewsItem(title="PNJ giảm sàn", source="A", url="https://example.com/a"),
            NewsItem(title="PNJ giảm sàn bản copy", source="B", url="https://example.com/a"),
            NewsItem(title="Người nhà lãnh đạo PNJ đăng ký mua cổ phiếu", source="C"),
        ]
    )

    assert [item.source for item in items] == ["A", "C"]


def test_fetch_news_catalyst_reports_disabled_source(monkeypatch) -> None:
    monkeypatch.setenv("VN_NEWS_CATALYST_ENABLED", "0")

    news = fetch_news_catalyst("PNJ")

    assert news.checked is False
    assert news.source == "agent-reach:multi-source"
    assert news.sourcesChecked[0].status == "disabled"
    assert news.dataQuality.status == "missing"


def test_public_warning_never_exposes_stack_trace_or_local_path() -> None:
    raw = "Unknown MCP server 'exa'\n at McpRuntime.connect (/Users/hiepln/.npm-global/lib/node_modules/tool/index.js:20:4)"

    warning = _public_warning("exa", raw)

    assert warning == "Exa tạm không khả dụng"
    assert "/Users/" not in warning
    assert "McpRuntime" not in warning


def test_resolve_tool_finds_user_npm_global_bin_when_service_path_is_minimal(tmp_path: Path, monkeypatch) -> None:
    mcporter = tmp_path / ".npm-global" / "bin" / "mcporter"
    mcporter.parent.mkdir(parents=True)
    mcporter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    mcporter.chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    assert _resolve_tool("mcporter", env_var="VN_NEWS_MCPORTER_PATH") == str(mcporter)


def test_fetch_news_catalyst_reuses_ttl_cache(monkeypatch) -> None:
    clear_news_cache()
    calls = {"google": 0}

    def fake_google(ticker: str, days: int):
        calls["google"] += 1
        return [NewsItem(title=f"{ticker} có tin mới", source="CafeF", url="https://example.com/news")]

    monkeypatch.setenv("VN_NEWS_CACHE_TTL_SECONDS", "300")
    monkeypatch.setattr("src.vn.news_catalyst._google_news_rss_items", fake_google)
    monkeypatch.setattr("src.vn.news_catalyst._direct_rss_items", lambda _ticker: [])
    monkeypatch.setattr("src.vn.news_catalyst._jina_search_items", lambda _ticker, _days: [])
    monkeypatch.setattr(
        "src.vn.news_catalyst._exa_items",
        lambda _ticker, _days: SourceResult(
            status=NewsSourceStatus(name="exa", status="partial", items=0, route="agent-reach:exa:mcporter"),
            items=[],
        ),
    )

    first = fetch_news_catalyst("FPT")
    second = fetch_news_catalyst("FPT")

    assert first.catalysts[0].url == "https://example.com/news"
    assert second.catalysts[0].url == "https://example.com/news"
    assert calls["google"] == 1


def test_fetch_news_catalyst_runs_independent_sources_concurrently(monkeypatch) -> None:
    clear_news_cache()
    barrier = threading.Barrier(4, timeout=2)

    def empty_source(*_args):
        barrier.wait()
        return []

    def empty_exa(*_args):
        barrier.wait()
        return SourceResult(
            status=NewsSourceStatus(name="exa", status="partial", items=0, route="agent-reach:exa:mcporter"),
            items=[],
        )

    monkeypatch.setenv("VN_NEWS_CACHE_TTL_SECONDS", "0")
    monkeypatch.setattr("src.vn.news_catalyst._google_news_rss_items", empty_source)
    monkeypatch.setattr("src.vn.news_catalyst._direct_rss_items", empty_source)
    monkeypatch.setattr("src.vn.news_catalyst._jina_search_items", empty_source)
    monkeypatch.setattr("src.vn.news_catalyst._exa_items", empty_exa)

    news = fetch_news_catalyst("FPT")

    assert [source.name for source in news.sourcesChecked] == [
        "google_news_rss",
        "direct_vn_rss",
        "jina_reader",
        "exa",
    ]
