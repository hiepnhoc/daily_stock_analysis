# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd

from src.vn.analysis.action_plan import build_action_plan
from src.vn.data import provider, ssi_iboard
from src.vn.indicators.technicals import add_indicators, latest_technical_snapshot
from src.vn.news_catalyst import fetch_news_catalyst
from src.vn.schemas import DataQuality, TechnicalSnapshot, VNActionPlan, VNMarketContext


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _shared_knowledge_root() -> Path:
    # This VN web repo lives under <hermes-agent>/knowledge/daily_stock_analysis_vn.
    # Reports should be written to the shared Hermes knowledge folder, not inside the nested clone.
    for parent in Path(__file__).resolve().parents:
        if parent.name == "hermes-agent":
            return parent / "knowledge"
    return _repo_root() / "knowledge"


def _report_dir() -> Path:
    path = _shared_knowledge_root() / "stock-reports" / "vn-market"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _journal_path() -> Path:
    override = os.getenv("VN_MARKET_JOURNAL_PATH")
    if override:
        path = Path(override)
    else:
        path = _shared_knowledge_root() / "stock-reports" / "vn-market" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


_SECTOR_MAP = {
    "HPG": "Thép", "HSG": "Thép", "NKG": "Thép",
    "FPT": "Công nghệ", "CMG": "Công nghệ", "CTR": "Công nghệ",
    "SSI": "Chứng khoán", "VCI": "Chứng khoán", "VND": "Chứng khoán", "HCM": "Chứng khoán",
    "TCB": "Ngân hàng", "CTG": "Ngân hàng", "VCB": "Ngân hàng", "MBB": "Ngân hàng", "ACB": "Ngân hàng",
    "MWG": "Bán lẻ", "FRT": "Bán lẻ", "DGW": "Bán lẻ",
    "VHM": "Bất động sản", "NLG": "Bất động sản", "KDH": "Bất động sản", "DXG": "Bất động sản",
    "GAS": "Dầu khí", "PLX": "Dầu khí", "PVD": "Dầu khí", "PVS": "Dầu khí",
}

_TICKER_NAME_MAP = {
    "ACB": "Ngân hàng Á Châu",
    "CTG": "VietinBank",
    "DGW": "Digiworld",
    "DXG": "Đất Xanh Group",
    "FPT": "FPT Corp",
    "FRT": "FPT Retail",
    "GAS": "PV GAS",
    "HCM": "Chứng khoán HSC",
    "HPG": "Hòa Phát",
    "HSG": "Hoa Sen Group",
    "KDH": "Khang Điền",
    "MBB": "MBBank",
    "MWG": "Thế Giới Di Động",
    "NKG": "Nam Kim",
    "NLG": "Nam Long",
    "PLX": "Petrolimex",
    "PVD": "PV Drilling",
    "PVS": "Dịch vụ Kỹ thuật Dầu khí",
    "SHB": "Ngân hàng SHB",
    "SSI": "Chứng khoán SSI",
    "TCB": "Techcombank",
    "VCB": "Vietcombank",
    "VCI": "Chứng khoán Vietcap",
    "VHM": "Vinhomes",
    "VIX": "Chứng khoán VIX",
    "VND": "Chứng khoán VNDirect",
}


def _technical_for_ticker(ticker: str) -> tuple[TechnicalSnapshot | None, Dict[str, DataQuality]]:
    df = provider.get_daily_bars(ticker, days=260)
    if df is None or df.empty:
        return None, {"ohlcv": DataQuality(status="missing", source="vndirect", warnings=["no_ohlcv_data"])}
    enriched = add_indicators(df)
    snapshot = latest_technical_snapshot(enriched)
    return TechnicalSnapshot(**snapshot), {"ohlcv": DataQuality(status="available", source="vndirect")}


def get_market_overview() -> dict:
    market = build_market_context()
    breadth_snapshot = ssi_iboard.fetch_exchange_breadth("hose")
    breadth = {
        "advancers": int(breadth_snapshot.get("advancers") or 0),
        "decliners": int(breadth_snapshot.get("decliners") or 0),
        "ceiling": int(breadth_snapshot.get("ceiling") or 0),
        "floor": int(breadth_snapshot.get("floor") or 0),
        "unchanged": int(breadth_snapshot.get("unchanged") or 0),
    }
    warnings = list(market.warnings)
    if not breadth_snapshot:
        warnings.append("Không lấy được SSI iBoard breadth, breadth đang để 0")
    return {
        "refDate": datetime.now().date().isoformat(),
        "indices": [
            {
                "code": "VNINDEX",
                "name": "VNINDEX",
                "close": market.vnindexClose,
                "changePct": market.vnindexChangePct,
                "volume": None,
                "value": None,
            }
        ],
        "breadth": breadth,
        "liquidity": {"totalValue": breadth_snapshot.get("totalValue"), "vs20dPct": None},
        "marketBias": market.marketBias,
        "warnings": warnings,
    }


def build_market_context() -> VNMarketContext:
    df = provider.get_daily_bars("VNINDEX", days=260)
    if df is None or df.empty:
        return VNMarketContext(
            marketBias="neutral",
            warnings=["Không lấy được VNINDEX, dùng market bias neutral"],
            dataQuality={"vnindex": DataQuality(status="missing", source="vndirect")},
        )
    enriched = add_indicators(df)
    snap = latest_technical_snapshot(enriched)
    close = snap.get("close")
    ema20 = snap.get("ema20")
    ema60 = snap.get("ema60")
    rsi = snap.get("rsi14")
    bias = "neutral"
    warnings: List[str] = []
    if close and ema20 and close < ema20:
        bias = "cautious"
        warnings.append("VNINDEX dưới EMA20, ưu tiên giảm size")
    if close and ema60 and close < ema60:
        bias = "bearish"
        warnings.append("VNINDEX dưới EMA60, không mua đuổi")
    if close and ema20 and close > ema20 and (rsi is None or rsi < 72):
        bias = "bullish"
    return VNMarketContext(
        marketBias=bias,
        vnindexClose=close,
        warnings=warnings,
        dataQuality={"vnindex": DataQuality(status="available", source="vndirect")},
    )


def analyze_ticker(ticker: str, market: VNMarketContext | None = None, include_news: bool = True) -> VNActionPlan:
    symbol = ticker.upper().strip()
    technical, quality = _technical_for_ticker(symbol)
    if technical is None:
        return VNActionPlan(
            ticker=symbol,
            action="avoid",
            score=0,
            confidence=0.0,
            reasons=[],
            riskFlags=["Không có dữ liệu OHLCV", "chưa kiểm chứng news/catalyst"],
            dataQuality=quality,
        )
    plan = build_action_plan(symbol, technical, market or build_market_context())
    plan.dataQuality.update(quality)
    if include_news:
        news = fetch_news_catalyst(symbol)
        plan.newsCatalyst = news
        plan.dataQuality["news"] = news.dataQuality
        if news.checked:
            plan.riskFlags = [flag for flag in plan.riskFlags if flag != "chưa kiểm chứng news/catalyst"]
        plan.riskFlags.extend(flag for flag in news.riskFlags if flag not in plan.riskFlags)
        if news.catalysts:
            plan.reasons.append(f"News/catalyst: tìm thấy {len(news.catalysts)} tin public web cần đọc kèm chart")
    return plan


def _chart_float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), 4)


def ticker_chart(ticker: str, days: int = 160) -> dict:
    """Return compact OHLCV + VN T+ moving-average data for charting."""
    symbol = ticker.upper().strip()
    lookback = max(int(days or 160), 60)
    # Fetch enough history for MA200, then trim to requested chart window.
    df = provider.get_daily_bars(symbol, days=max(260, lookback + 220))
    if df is None or df.empty:
        return {
            "ticker": symbol,
            "items": [],
            "dataQuality": {"ohlcv": DataQuality(status="missing", source="vndirect", warnings=["no_ohlcv_data"]).model_dump(mode="json")},
        }
    enriched = add_indicators(df).tail(lookback)
    items = []
    for _, row in enriched.iterrows():
        raw_date = row.get("date")
        if isinstance(raw_date, pd.Timestamp):
            date = raw_date.date().isoformat()
        else:
            date = str(raw_date)[:10]
        items.append(
            {
                "date": date,
                "open": _chart_float(row.get("open")),
                "high": _chart_float(row.get("high")),
                "low": _chart_float(row.get("low")),
                "close": _chart_float(row.get("close")),
                "volume": _chart_float(row.get("volume")),
                "ema20": _chart_float(row.get("EMA20")),
                "ema60": _chart_float(row.get("EMA60")),
                "ma50": _chart_float(row.get("MA50")),
                "ma200": _chart_float(row.get("MA200")),
                "vol20": _chart_float(row.get("VOL20")),
                "rsi14": _chart_float(row.get("RSI14")),
                "macd": _chart_float(row.get("MACD")),
                "macdSignal": _chart_float(row.get("MACD_SIGNAL")),
                "macdHist": _chart_float(row.get("MACD_HIST")),
            }
        )
    return {
        "ticker": symbol,
        "items": items,
        "dataQuality": {"ohlcv": DataQuality(status="available", source="vndirect").model_dump(mode="json")},
    }


def scan_watchlist(watchlist: List[str], mode: str = "tplus") -> dict:
    market = build_market_context()
    items = [analyze_ticker(ticker, market=market, include_news=False) for ticker in watchlist if ticker.strip()]
    items.sort(key=lambda item: item.score, reverse=True)
    return {"items": [item.model_dump(mode="json") for item in items]}


def portfolio_check(holdings: List[dict]) -> dict:
    items = []
    market = build_market_context()
    for holding in holdings:
        ticker = str(holding.get("ticker") or "").upper().strip()
        if not ticker:
            continue
        quantity = int(holding.get("quantity") or 0)
        avg_cost = float(holding.get("avgCost") or 0)
        sellable_qty = int(holding.get("sellableQty") or 0)
        pending_qty = int(holding.get("pendingQty") or max(quantity - sellable_qty, 0))
        quote = ssi_iboard.fetch_live_quote(ticker)
        price = quote.get("price")
        plan = analyze_ticker(ticker, market=market, include_news=False)
        if price is None and plan.technical and plan.technical.close is not None:
            price = plan.technical.close
        current_price = float(price or 0)
        # SSI iBoard often returns raw VND prices (e.g. 23450), while VN daily bars
        # and user-entered cost are usually in thousand-VND units (e.g. 23.45).
        if current_price > 1000 and avg_cost and avg_cost < 1000:
            current_price = current_price / 1000
        market_value = current_price * quantity
        cost_value = avg_cost * quantity
        pl = market_value - cost_value if current_price and avg_cost else None
        pl_pct = (pl / cost_value * 100) if pl is not None and cost_value else None
        today_plan: List[str] = []
        if sellable_qty <= 0:
            today_plan.append("Khả dụng = 0, hôm nay không bán được; chỉ lập kịch bản khi hàng về")
        else:
            if plan.targets:
                today_plan.append(f"Nếu hồi vùng {plan.targets[0]} có thể chốt/giảm một phần trong {sellable_qty} cp khả dụng")
            if plan.stopLoss:
                today_plan.append(f"Nếu thủng {plan.stopLoss} thì giảm rủi ro phần bán được")
            if plan.action in {"avoid", "sell_reduce"}:
                today_plan.append("Setup yếu, ưu tiên hồi để giảm tỷ trọng, không mua thêm")
        pending_plan = "Không có hàng chờ về" if pending_qty <= 0 else f"{pending_qty} cp chờ về: xử lý khi hàng về, không giả định là core"
        items.append(
            {
                "ticker": ticker,
                "name": _TICKER_NAME_MAP.get(ticker),
                "quantity": quantity,
                "avgCost": avg_cost,
                "currentPrice": round(current_price, 2) if current_price else None,
                "marketValue": round(market_value, 0) if current_price else None,
                "pl": round(pl, 0) if pl is not None else None,
                "plPct": round(pl_pct, 2) if pl_pct is not None else None,
                "sellableQty": sellable_qty,
                "pendingQty": pending_qty,
                "action": plan.action,
                "stopLoss": plan.stopLoss,
                "targets": plan.targets,
                "todayPlan": today_plan,
                "pendingPlan": pending_plan,
                "riskFlags": plan.riskFlags,
            }
        )
    return {"items": items}


def sector_flow(watchlist: List[str], mode: str = "tplus") -> dict:
    scan = scan_watchlist(watchlist, mode=mode)
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in scan["items"]:
        sector = _SECTOR_MAP.get(item["ticker"], "Khác")
        groups[sector].append(item)
    rows = []
    for sector, members in groups.items():
        avg_score = sum(member.get("score", 0) for member in members) / max(len(members), 1)
        strong = [m["ticker"] for m in members if m.get("action") in {"watch_breakout", "buy_zone", "watch"}]
        risks = [flag for member in members for flag in member.get("riskFlags", [])]
        rows.append(
            {
                "sector": sector,
                "tickers": [m["ticker"] for m in members],
                "avgScore": round(avg_score, 1),
                "candidateCount": len(strong),
                "bias": "positive" if avg_score >= 65 else "neutral" if avg_score >= 45 else "weak",
                "topCandidates": strong[:5],
                "riskFlags": sorted(set(risks))[:5],
            }
        )
    rows.sort(key=lambda row: (row["avgScore"], row["candidateCount"]), reverse=True)
    return {"items": rows}


def alerts_check(watchlist: List[str], mode: str = "tplus") -> dict:
    scan = scan_watchlist(watchlist, mode=mode)
    items = []
    for plan in scan["items"]:
        alerts = []
        technical = plan.get("technical") or {}
        close = technical.get("close")
        rsi = technical.get("rsi14")
        volume_ratio = technical.get("volumeRatio")
        stop = plan.get("stopLoss")
        breakout = plan.get("breakoutTrigger")
        if close is not None and stop is not None and close <= stop * 1.015:
            alerts.append({"type": "stop_near", "message": f"{plan['ticker']} sát/thủng vùng stop {stop}"})
        if close is not None and breakout is not None and close >= breakout * 0.99:
            alerts.append({"type": "breakout_near", "message": f"{plan['ticker']} sát vùng breakout {breakout}"})
        if rsi is not None and rsi >= 75:
            alerts.append({"type": "hot_rsi", "message": f"{plan['ticker']} RSI14 cao, tránh FOMO"})
        if volume_ratio is not None and volume_ratio >= 1.5:
            alerts.append({"type": "volume_spike", "message": f"{plan['ticker']} volume spike > 1.5x Vol20"})
        if not alerts:
            alerts.append({"type": "watch", "message": f"{plan['ticker']} chưa có trigger khẩn, tiếp tục theo dõi setup"})
        items.append({"ticker": plan["ticker"], "action": plan.get("action"), "score": plan.get("score"), "alerts": alerts})
    return {"items": items}


def alert_rules_check(rules: List[dict]) -> dict:
    """Evaluate user-defined alert rules against latest VN technical plan."""
    items = []
    cache: dict[str, VNActionPlan] = {}
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        ticker = str(rule.get("ticker") or "").upper().strip()
        if not ticker:
            continue
        if ticker not in cache:
            cache[ticker] = analyze_ticker(ticker, include_news=False)
        plan = cache[ticker].model_dump(mode="json")
        technical = plan.get("technical") or {}
        condition = str(rule.get("condition") or "").strip()
        threshold = float(rule.get("threshold") or 0)
        close = technical.get("close")
        rsi = technical.get("rsi14")
        volume_ratio = technical.get("volumeRatio")
        breakout = plan.get("breakoutTrigger")
        stop = plan.get("stopLoss")
        current_value = None
        triggered = False
        if condition == "price_above":
            current_value = close
            triggered = close is not None and close >= threshold
        elif condition == "price_below":
            current_value = close
            triggered = close is not None and close <= threshold
        elif condition == "rsi_above":
            current_value = rsi
            triggered = rsi is not None and rsi >= threshold
        elif condition == "rsi_below":
            current_value = rsi
            triggered = rsi is not None and rsi <= threshold
        elif condition == "volume_ratio_above":
            current_value = volume_ratio
            triggered = volume_ratio is not None and volume_ratio >= threshold
        elif condition == "near_breakout":
            current_value = close
            pct = threshold / 100 if threshold else 0.01
            triggered = close is not None and breakout is not None and close >= breakout * (1 - pct)
        elif condition == "near_stop":
            current_value = close
            pct = threshold / 100 if threshold else 0.01
            triggered = close is not None and stop is not None and close <= stop * (1 + pct)
        else:
            items.append({"rule": rule, "ticker": ticker, "triggered": False, "message": f"Điều kiện không hỗ trợ: {condition}", "currentValue": None})
            continue
        label = {
            "price_above": f"giá >= {threshold}",
            "price_below": f"giá <= {threshold}",
            "rsi_above": f"RSI >= {threshold}",
            "rsi_below": f"RSI <= {threshold}",
            "volume_ratio_above": f"volume >= {threshold}x Vol20",
            "near_breakout": f"sát breakout trong {threshold or 1}%",
            "near_stop": f"sát stop trong {threshold or 1}%",
        }.get(condition, condition)
        state = "TRIGGER" if triggered else "watch"
        items.append(
            {
                "rule": rule,
                "ticker": ticker,
                "condition": condition,
                "triggered": triggered,
                "currentValue": round(float(current_value), 4) if current_value is not None else None,
                "message": f"{state}: {ticker} {label}; hiện tại {round(float(current_value), 4) if current_value is not None else '--'}",
                "planAction": plan.get("action"),
                "score": plan.get("score"),
            }
        )
    items.sort(key=lambda item: (not item.get("triggered", False), item.get("ticker", "")))
    return {"items": items}


def create_journal_signal(payload: dict) -> dict:
    item = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "ticker": str(payload.get("ticker") or "").upper().strip(),
        "action": payload.get("action"),
        "score": payload.get("score"),
        "note": payload.get("note") or "",
    }
    with _journal_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def list_journal_signals(limit: int = 100) -> dict:
    path = _journal_path()
    if not path.exists():
        return {"items": []}
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {"items": list(reversed(rows[-limit:]))}


def daily_playbook(watchlist: List[str], holdings: List[dict] | None = None, mode: str = "tplus") -> dict:
    """Create an action-first daily VN T+ playbook for the web dashboard."""
    overview = get_market_overview()
    scan = scan_watchlist(watchlist, mode=mode)
    portfolio = portfolio_check(holdings or []) if holdings else {"items": []}
    items = scan["items"]
    sector_groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        sector_groups[_SECTOR_MAP.get(item["ticker"], "Khác")].append(item)
    sector_items = []
    for sector_name, members in sector_groups.items():
        avg_score = sum(member.get("score", 0) for member in members) / max(len(members), 1)
        strong = [m["ticker"] for m in members if m.get("action") in {"watch_breakout", "buy_zone", "watch", "hold"}]
        sector_items.append(
            {
                "sector": sector_name,
                "tickers": [m["ticker"] for m in members],
                "avgScore": round(avg_score, 1),
                "candidateCount": len(strong),
                "bias": "positive" if avg_score >= 65 else "neutral" if avg_score >= 45 else "weak",
                "topCandidates": strong[:5],
                "riskFlags": sorted({flag for member in members for flag in member.get("riskFlags", [])})[:5],
            }
        )
    sector_items.sort(key=lambda row: (row["avgScore"], row["candidateCount"]), reverse=True)
    top_setups = [item for item in items if item.get("action") in {"buy_zone", "watch_breakout", "watch", "hold"}][:5]
    avoid_list = [item for item in items if item.get("action") in {"avoid", "sell_reduce"}][:5]
    market_bias = overview.get("marketBias") or "neutral"
    breadth = overview.get("breadth") or {}
    advancers = int(breadth.get("advancers") or 0)
    decliners = int(breadth.get("decliners") or 0)
    summary = [
        f"Market bias: {market_bias}; breadth {advancers}/{decliners}.",
        "Ưu tiên size nhỏ/vừa, không FOMO nếu giá đã kéo xa EMA20.",
    ]
    if market_bias in {"cautious", "bearish"} or decliners > advancers:
        summary.append("Thị trường chưa thật sự thuận, ưu tiên giữ tiền mặt và chờ pullback/confirm.")
    elif top_setups:
        summary.append("Có thể tập trung theo dõi nhóm/mã score cao, chỉ mua khi về vùng hoặc breakout có volume.")
    portfolio_actions = []
    for item in portfolio["items"]:
        portfolio_actions.append(
            {
                "ticker": item["ticker"],
                "action": item.get("action"),
                "plPct": item.get("plPct"),
                "sellableQty": item.get("sellableQty"),
                "pendingQty": item.get("pendingQty"),
                "plan": item.get("todayPlan") or [],
                "pendingPlan": item.get("pendingPlan"),
            }
        )
    return {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "overview": overview,
        "summary": summary,
        "topSetups": top_setups,
        "avoidList": avoid_list,
        "sectorBias": sector_items[:5],
        "portfolioActions": portfolio_actions,
        "warnings": sorted(set((overview.get("warnings") or []) + ["chưa kiểm chứng news/catalyst"])),
    }


def export_report(watchlist: List[str], mode: str = "tplus") -> dict:
    scan = scan_watchlist(watchlist, mode=mode)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = _report_dir() / f"vn_tplus_{timestamp}"
    json_path = base.with_suffix(".json")
    html_path = base.with_suffix(".html")
    payload = {"generatedAt": datetime.now().isoformat(timespec="seconds"), "mode": mode, **scan}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = "\n".join(
        f"<tr><td>{item['ticker']}</td><td>{item['action']}</td><td>{item['score']}</td>"
        f"<td>{item.get('buyZone') or '--'}</td><td>{item.get('stopLoss') or '--'}</td>"
        f"<td>{' / '.join(map(str, item.get('targets') or []))}</td>"
        f"<td>{'; '.join(item.get('riskFlags') or [])}</td></tr>"
        for item in scan["items"]
    )
    html = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><title>VN T+ Report</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:32px;background:#0f172a;color:#e5e7eb}}table{{width:100%;border-collapse:collapse;background:#111827}}td,th{{border:1px solid #374151;padding:10px}}th{{background:#1f2937}}.warn{{color:#fbbf24}}</style>
</head><body><h1>VN Market / T+ Scan</h1><p>Generated: {payload['generatedAt']}</p><p class="warn">Không phải khuyến nghị đầu tư; chưa kiểm chứng news/catalyst nếu không có nguồn tin trong report.</p><table><thead><tr><th>Mã</th><th>Action</th><th>Score</th><th>Buy zone</th><th>Stop</th><th>Targets</th><th>Risk</th></tr></thead><tbody>{rows}</tbody></table></body></html>"""
    html_path.write_text(html, encoding="utf-8")
    return {"htmlPath": str(html_path), "jsonPath": str(json_path), "summary": f"Exported {len(scan['items'])} VN tickers"}
