# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from src.vn.analysis.action_plan import build_action_plan
from src.vn.data import provider, ssi_iboard
from src.vn.indicators.technicals import add_indicators, latest_technical_snapshot
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


def analyze_ticker(ticker: str, market: VNMarketContext | None = None) -> VNActionPlan:
    technical, quality = _technical_for_ticker(ticker)
    if technical is None:
        return VNActionPlan(
            ticker=ticker.upper().strip(),
            action="avoid",
            score=0,
            confidence=0.0,
            reasons=[],
            riskFlags=["Không có dữ liệu OHLCV", "chưa kiểm chứng news/catalyst"],
            dataQuality=quality,
        )
    plan = build_action_plan(ticker, technical, market or build_market_context())
    plan.dataQuality.update(quality)
    return plan


def scan_watchlist(watchlist: List[str], mode: str = "tplus") -> dict:
    market = build_market_context()
    items = [analyze_ticker(ticker, market=market) for ticker in watchlist if ticker.strip()]
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
        plan = analyze_ticker(ticker, market=market)
        if price is None and plan.technical and plan.technical.close is not None:
            price = plan.technical.close
        current_price = float(price or 0)
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
