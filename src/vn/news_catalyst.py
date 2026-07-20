# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List

from src.vn.schemas import DataQuality, NewsCatalyst, NewsItem, NewsSourceStatus


_MULTI_SOURCE = "agent-reach:multi-source"
_GOOGLE_NEWS_RSS_ROUTE = "agent-reach:rss:google-news"
_JINA_READER_ROUTE = "agent-reach:jina-reader"
_EXA_ROUTE = "agent-reach:exa:mcporter"
_DIRECT_RSS_ROUTE = "agent-reach:rss:direct"
_DEFAULT_TIMEOUT_SECONDS = 5
_SEARCH_SOURCES = ("CafeF", "Vietstock", "VNDIRECT", "SSI", "HoSE", "VnEconomy", "Tuổi Trẻ", "Lao Động", "Tin nhanh chứng khoán")
_DIRECT_RSS_FEEDS = (
    ("CafeF", "https://cafef.vn/thi-truong-chung-khoan.rss"),
    ("Vietstock", "https://vietstock.vn/chung-khoan.rss"),
    ("VnEconomy", "https://vneconomy.vn/chung-khoan.rss"),
    ("Tin nhanh chứng khoán", "https://www.tinnhanhchungkhoan.vn/chung-khoan.rss"),
)
_NEGATIVE_KEYWORDS = (
    "khởi tố", "bắt", "điều tra", "bán tháo", "giảm sàn", "dư bán sàn", "sàn phiên",
    "lỗ", "lỗ ròng", "phạt", "cảnh báo", "hủy niêm yết", "bị bán", "buôn lậu", "truy tố",
)
_POSITIVE_KEYWORDS = (
    "mua cổ phiếu", "đăng ký mua", "lợi nhuận tăng", "lãi tăng", "chia cổ tức", "cổ tức",
    "tăng trưởng", "vượt kế hoạch", "ký hợp đồng", "phát hành thành công", "mua lại cổ phiếu",
)
_HIGH_RISK_KEYWORDS = ("khởi tố", "bắt", "điều tra", "bán tháo", "giảm sàn", "dư bán sàn", "buôn lậu", "truy tố")
_LOW_IMPACT_KEYWORDS = ("nhắc lại", "dự kiến", "kế hoạch", "lịch", "thông báo")


def _public_warning(source: str, _raw_error: str | None = None) -> str:
    """Return a stable client-safe source status without leaking runtime details."""
    labels = {
        "exa": "Exa tạm không khả dụng",
        "google_news_rss": "Google News RSS tạm không khả dụng",
        "direct_vn_rss": "Nguồn RSS Việt Nam tạm không khả dụng",
        "jina_reader": "Jina Reader tạm không khả dụng",
    }
    return labels.get(source, "Nguồn tin tạm không khả dụng")


@dataclass
class SourceResult:
    status: NewsSourceStatus
    items: List[NewsItem]


def _enabled() -> bool:
    return os.getenv("VN_NEWS_CATALYST_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


def _fetch_text(url: str, timeout: int = _DEFAULT_TIMEOUT_SECONDS) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "agent-reach-vn-stock-news/1.0",
            "Accept": "application/rss+xml,application/json,text/markdown,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - public news pages only
        return response.read(512_000).decode("utf-8", errors="replace")


def _line_date(line: str) -> str | None:
    match = re.search(r"\b(20\d{2}[-/][01]?\d[-/][0-3]?\d|[0-3]?\d[-/][01]?\d[-/]20\d{2})\b", line)
    return match.group(1) if match else None


def _clean_title(line: str) -> str:
    line = html.unescape(line or "")
    line = re.sub(r"<script\b[^>]*>.*?</script>", " ", line, flags=re.IGNORECASE | re.DOTALL)
    line = re.sub(r"<style\b[^>]*>.*?</style>", " ", line, flags=re.IGNORECASE | re.DOTALL)
    line = re.sub(r"<[^>]+>", " ", line)
    line = re.sub(r"^#+\s*", "", line.strip())
    line = re.sub(r"^[-*]\s*", "", line)
    line = re.sub(r"\s+", " ", line)
    return line[:220]


def _classify_tone(text: str) -> str:
    haystack = text.lower()
    negative = any(keyword in haystack for keyword in _NEGATIVE_KEYWORDS)
    positive = any(keyword in haystack for keyword in _POSITIVE_KEYWORDS)
    if negative and positive:
        return "mixed"
    if negative:
        return "negative"
    if positive:
        return "positive"
    return "neutral"


def _classify_impact(text: str) -> str:
    haystack = text.lower()
    if any(keyword in haystack for keyword in _HIGH_RISK_KEYWORDS):
        return "high"
    if any(keyword in haystack for keyword in _LOW_IMPACT_KEYWORDS):
        return "low"
    return "medium"


def _decorate_item(item: NewsItem, route: str) -> NewsItem:
    text = f"{item.title} {item.summary}"
    item.tone = _classify_tone(text)  # type: ignore[assignment]
    item.impact = _classify_impact(text)  # type: ignore[assignment]
    item.sourceRoute = route
    return item


def _dedupe_items(items: List[NewsItem], limit: int = 8) -> List[NewsItem]:
    deduped: List[NewsItem] = []
    seen: set[str] = set()
    for item in items:
        key = (item.url or re.sub(r"\W+", " ", item.title.lower())).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def _extract_search_items(markdown: str, ticker: str, route: str, limit: int = 5) -> List[NewsItem]:
    items: List[NewsItem] = []
    seen: set[str] = set()
    ticker_upper = ticker.upper()
    lines = [line.strip() for line in markdown.splitlines() if line.strip()]

    for idx, line in enumerate(lines):
        if ticker_upper not in line.upper():
            continue
        if not any(source.lower() in line.lower() for source in _SEARCH_SOURCES) and "cổ phiếu" not in line.lower():
            continue

        nearby = " ".join(lines[idx : idx + 4])
        urls = re.findall(r"https?://[^\s)\]]+", nearby)
        url = urls[0].rstrip(".,") if urls else None
        title = _clean_title(line)
        key = (url or title).lower()
        if key in seen or len(title) < 12:
            continue
        seen.add(key)
        source = next((source for source in _SEARCH_SOURCES if source.lower() in nearby.lower()), "public web")
        items.append(
            _decorate_item(
                NewsItem(
                    title=title,
                    source=source,
                    date=_line_date(nearby),
                    url=url,
                    summary=_clean_title(nearby)[:280],
                ),
                route,
            )
        )
        if len(items) >= limit:
            break
    return items


def _extract_rss_items(xml_text: str, route: str, ticker: str | None = None, limit: int = 5) -> List[NewsItem]:
    root = ET.fromstring(xml_text)
    items: List[NewsItem] = []
    ticker_upper = ticker.upper() if ticker else None
    for node in root.findall(".//item"):
        title = _clean_title(node.findtext("title") or "")
        if not title:
            continue
        description = _clean_title(node.findtext("description") or "")
        if ticker_upper and ticker_upper not in f"{title} {description}".upper():
            continue
        source_node = node.find("source")
        source = (source_node.text if source_node is not None and source_node.text else "RSS").strip()
        items.append(
            _decorate_item(
                NewsItem(
                    title=title,
                    source=source,
                    date=node.findtext("pubDate"),
                    url=node.findtext("link"),
                    summary=description or title,
                ),
                route,
            )
        )
        if len(items) >= limit:
            break
    return items


def _source_result(name: str, route: str, fn: Callable[[], List[NewsItem]]) -> SourceResult:
    try:
        items = fn()
    except (ET.ParseError, urllib.error.URLError, TimeoutError, OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return SourceResult(
            status=NewsSourceStatus(name=name, status="failed", items=0, route=route, warning=_public_warning(name, str(exc))),
            items=[],
        )
    return SourceResult(
        status=NewsSourceStatus(name=name, status="available" if items else "partial", items=len(items), route=route, warning=None if items else "no_matching_items"),
        items=items,
    )


def _google_news_rss_items(ticker: str, days: int) -> List[NewsItem]:
    query = f"{ticker.upper()} cổ phiếu when:{days}d"
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "vi", "gl": "VN", "ceid": "VN:vi"}
    )
    return _extract_rss_items(_fetch_text(url, timeout=min(_DEFAULT_TIMEOUT_SECONDS, 4)), _GOOGLE_NEWS_RSS_ROUTE, limit=5)


def _jina_search_items(ticker: str, days: int) -> List[NewsItem]:
    query = f"{ticker.upper()} cổ phiếu tin mới {days} ngày CafeF Vietstock VNDIRECT SSI VnEconomy"
    search_url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "setlang": "vi"})
    jina_url = "https://r.jina.ai/http://" + search_url.removeprefix("https://")
    body = _fetch_text(jina_url, timeout=int(os.getenv("VN_NEWS_CATALYST_TIMEOUT", _DEFAULT_TIMEOUT_SECONDS)))
    return _extract_search_items(body, ticker, _JINA_READER_ROUTE)


def _direct_rss_items(ticker: str) -> List[NewsItem]:
    items: List[NewsItem] = []
    for _source_name, feed_url in _DIRECT_RSS_FEEDS:
        try:
            items.extend(_extract_rss_items(_fetch_text(feed_url, timeout=3), _DIRECT_RSS_ROUTE, ticker=ticker, limit=3))
        except (ET.ParseError, urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue
    return _dedupe_items(items, limit=5)


def _exa_items(ticker: str, days: int) -> SourceResult:
    if not shutil.which("mcporter"):
        return SourceResult(
            status=NewsSourceStatus(name="exa", status="missing_tool", items=0, route=_EXA_ROUTE, warning="mcporter_not_found"),
            items=[],
        )
    query = f'{ticker.upper()} cổ phiếu tin mới {days} ngày khởi tố giảm sàn CafeF Vietstock VnEconomy Tin nhanh chứng khoán'
    expr = f'exa.web_search_exa(query: "{query}", numResults: 8)'
    try:
        completed = subprocess.run(  # noqa: S603 - fixed executable + public search query only
            ["mcporter", "call", expr],
            check=False,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("VN_NEWS_EXA_TIMEOUT", "12")),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return SourceResult(
            status=NewsSourceStatus(name="exa", status="failed", items=0, route=_EXA_ROUTE, warning=_public_warning("exa", str(exc))),
            items=[],
        )
    if completed.returncode != 0:
        return SourceResult(
            status=NewsSourceStatus(name="exa", status="failed", items=0, route=_EXA_ROUTE, warning=_public_warning("exa", completed.stderr or completed.stdout)),
            items=[],
        )
    items = _extract_search_items(completed.stdout, ticker, _EXA_ROUTE, limit=5)
    return SourceResult(
        status=NewsSourceStatus(name="exa", status="available" if items else "partial", items=len(items), route=_EXA_ROUTE, warning=None if items else "no_matching_items"),
        items=items,
    )


def _sentiment_for(items: List[NewsItem]) -> str:
    tones = [item.tone for item in items]
    if not tones:
        return "neutral"
    positives = tones.count("positive")
    negatives = tones.count("negative")
    mixed = tones.count("mixed")
    if mixed or (positives and negatives):
        return "mixed"
    if negatives:
        return "negative"
    if positives:
        return "positive"
    return "neutral"


def fetch_news_catalyst(ticker: str, days: int = 7) -> NewsCatalyst:
    """Best-effort Agent Reach-compatible multi-source news check for VN Analyze.

    Uses zero-config public routes first (Google News RSS, direct RSS, Jina Reader)
    and optionally calls Agent Reach's Exa route through mcporter when available.
    Every source is fail-open so chart analysis still works if a route times out.
    """

    symbol = ticker.upper().strip()
    if not symbol:
        return NewsCatalyst(
            checked=False,
            source=_MULTI_SOURCE,
            freshnessWindow=f"{days}d",
            sentiment="unknown",
            catalysts=[],
            riskFlags=["ticker trống, chưa kiểm chứng news/catalyst"],
            sourcesChecked=[],
            dataQuality=DataQuality(status="missing", source=_MULTI_SOURCE, warnings=["empty_ticker"]),
        )

    if not _enabled():
        return NewsCatalyst(
            checked=False,
            source=_MULTI_SOURCE,
            freshnessWindow=f"{days}d",
            sentiment="unknown",
            catalysts=[],
            riskFlags=["news/catalyst check đang tắt bởi VN_NEWS_CATALYST_ENABLED"],
            sourcesChecked=[NewsSourceStatus(name="multi-source", status="disabled", items=0, route=_MULTI_SOURCE, warning="disabled_by_env")],
            dataQuality=DataQuality(status="missing", source=_MULTI_SOURCE, warnings=["disabled"]),
        )

    results = [
        _source_result("google_news_rss", _GOOGLE_NEWS_RSS_ROUTE, lambda: _google_news_rss_items(symbol, days)),
        _source_result("direct_vn_rss", _DIRECT_RSS_ROUTE, lambda: _direct_rss_items(symbol)),
        _source_result("jina_reader", _JINA_READER_ROUTE, lambda: _jina_search_items(symbol, days)),
        _exa_items(symbol, days),
    ]
    items = _dedupe_items([item for result in results for item in result.items], limit=int(os.getenv("VN_NEWS_CATALYST_LIMIT", "8")))
    statuses = [result.status for result in results]
    warnings = [f"{status.name}: {status.warning}" for status in statuses if status.warning and status.status in {"failed", "missing_tool"}]

    risk_flags: List[str] = []
    if not items:
        risk_flags.append(f"Đã check multi-source public web nhưng chưa thấy catalyst nổi bật cho {symbol} trong cửa sổ {days} ngày")
    if any(item.tone in {"negative", "mixed"} and item.impact == "high" for item in items):
        risk_flags.append("Có news/catalyst tiêu cực impact cao, phải đọc bài gốc trước khi vào lệnh")
    if warnings:
        risk_flags.append(f"Một số route tin tức chưa khả dụng/lỗi: {'; '.join(warnings)}")

    any_success = any(status.status in {"available", "partial"} for status in statuses)
    return NewsCatalyst(
        checked=any_success,
        source=_MULTI_SOURCE,
        checkedAt=datetime.now().isoformat(timespec="seconds"),
        freshnessWindow=f"{days}d",
        sentiment=_sentiment_for(items) if items else "neutral",
        catalysts=items,
        sourcesChecked=statuses,
        riskFlags=risk_flags,
        dataQuality=DataQuality(
            status="available" if items else ("partial" if any_success else "failed"),
            source=_MULTI_SOURCE,
            warnings=warnings if warnings else ([] if items else ["no_high_signal_public_web_item"]),
        ),
    )
