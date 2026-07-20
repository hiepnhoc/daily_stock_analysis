# -*- coding: utf-8 -*-
from __future__ import annotations

from src.vn.news_catalyst import _dedupe_items, _decorate_item, _public_warning, fetch_news_catalyst
from src.vn.schemas import NewsItem


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
