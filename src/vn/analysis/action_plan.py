# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Optional

from src.vn.schemas import DataQuality, TechnicalSnapshot, VNAction, VNActionPlan, VNMarketContext

_NEWS_UNCHECKED_FLAG = "chưa kiểm chứng news/catalyst"


def _num(value: Optional[float], default: float = 0.0) -> float:
    return float(value) if value is not None else default


def _round_price(value: float) -> float:
    if value >= 100:
        return round(value, 1)
    return round(value, 2)


def _score_technical(technical: TechnicalSnapshot, market: VNMarketContext) -> tuple[int, List[str], List[str]]:
    score = 0
    reasons: List[str] = []
    risks: List[str] = []
    close = _num(technical.close)

    market_points = {"bullish": 18, "neutral": 12, "cautious": 7, "bearish": 2}.get(market.marketBias, 10)
    score += market_points
    if market.marketBias in {"cautious", "bearish"}:
        risks.append("VNINDEX/thị trường chưa ủng hộ, giảm size và tránh FOMO")
    elif market.marketBias == "bullish":
        reasons.append("Bối cảnh thị trường ủng hộ hơn cho setup T+")

    if technical.ema20 and close > technical.ema20:
        score += 9
        reasons.append("Giá đang giữ trên EMA20")
    else:
        risks.append("Giá chưa giữ được EMA20")
    if technical.ema60 and close > technical.ema60:
        score += 6
        reasons.append("Giá trên EMA60, xu hướng trung hạn chưa xấu")
    if technical.ma50 and close > technical.ma50:
        score += 5
    if technical.ma200 and close > technical.ma200:
        score += 5

    rsi = technical.rsi14
    if rsi is not None:
        if 45 <= rsi <= 70:
            score += 12
            reasons.append("RSI14 nằm trong vùng còn dư địa")
        elif rsi > 75:
            score += 3
            risks.append("RSI14 cao, dễ thành mua đuổi")
        elif rsi < 35:
            score += 2
            risks.append("RSI14 yếu, momentum chưa xác nhận")
        else:
            score += 7

    if technical.macdHist is not None and technical.macdHist > 0:
        score += 8
        reasons.append("MACD histogram dương/cải thiện")
    elif technical.macd is not None and technical.macdSignal is not None and technical.macd > technical.macdSignal:
        score += 6

    vr = technical.volumeRatio
    if vr is not None:
        if vr >= 1.3:
            score += 14
            reasons.append("Volume vượt Vol20, có xác nhận dòng tiền")
        elif vr >= 0.8:
            score += 8
        else:
            score += 4
            risks.append("Volume chưa xác nhận")

    if technical.atr14 and close:
        atr_pct = technical.atr14 / close
        if atr_pct <= 0.04:
            score += 10
            reasons.append("Biên ATR vừa phải, dễ quản trị rủi ro")
        elif atr_pct <= 0.07:
            score += 6
        else:
            score += 2
            risks.append("ATR cao, biến động rộng")
    else:
        score += 4

    return min(score, 100), reasons, risks


def _action_from_score(score: int, technical: TechnicalSnapshot, market: VNMarketContext) -> VNAction:
    close = _num(technical.close)
    extended = bool(technical.ema20 and close > technical.ema20 * 1.08) or bool(technical.rsi14 and technical.rsi14 > 75)
    if extended:
        return "avoid"
    if market.marketBias == "bearish":
        return "watch" if score >= 60 else "avoid"
    if score >= 75:
        return "watch_breakout"
    if score >= 60:
        return "watch"
    if score >= 45:
        return "hold"
    return "avoid"


def build_action_plan(ticker: str, technical: TechnicalSnapshot, market: VNMarketContext | None = None) -> VNActionPlan:
    market = market or VNMarketContext()
    score, reasons, risks = _score_technical(technical, market)
    action = _action_from_score(score, technical, market)
    close = _num(technical.close)
    atr = _num(technical.atr14, close * 0.025 if close else 0)
    ema20 = _num(technical.ema20, close)
    ma50 = _num(technical.ma50, ema20)

    support = min(x for x in [ema20, ma50, close] if x > 0) if close else 0
    buy_low = _round_price(max(support, close - atr * 1.2)) if close else None
    buy_high = _round_price(max(support, close - atr * 0.3)) if close else None
    buy_zone = (buy_low, buy_high) if buy_low and buy_high and buy_low <= buy_high else None
    breakout = _round_price(close + max(atr * 0.35, close * 0.01)) if close else None
    stop = _round_price(max(0, min(support, close) - max(atr * 1.1, close * 0.025))) if close else None
    targets = []
    if close and stop and close > stop:
        risk = close - stop
        targets = [_round_price(close + risk * 1.6), _round_price(close + risk * 2.4)]

    size = 0
    if action in {"watch_breakout", "buy_zone"}:
        size = 20
    elif action == "watch":
        size = 10
    if market.marketBias == "bearish":
        size = min(size, 10)
    elif market.marketBias == "cautious":
        size = min(size, 15)

    all_risks = [*risks, *market.warnings]
    if _NEWS_UNCHECKED_FLAG not in all_risks:
        all_risks.append(_NEWS_UNCHECKED_FLAG)

    confidence = max(0.1, min(0.85, score / 100 - (0.1 if market.marketBias in {"cautious", "bearish"} else 0)))
    return VNActionPlan(
        ticker=ticker.upper().strip(),
        action=action,
        score=score,
        confidence=round(confidence, 2),
        buyZone=buy_zone,
        breakoutTrigger=breakout,
        stopLoss=stop,
        targets=targets,
        positionSizePct=size,
        reasons=reasons,
        riskFlags=all_risks,
        dataQuality={"ohlcv": DataQuality(status="available", source="vndirect")},
        technical=technical,
    )
