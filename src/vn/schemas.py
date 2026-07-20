# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

DataStatus = Literal["available", "fallback", "partial", "missing", "failed", "mock"]
MarketBias = Literal["bullish", "neutral", "cautious", "bearish"]
VNAction = Literal["buy_zone", "watch_breakout", "watch", "hold", "avoid", "sell_reduce"]


class DataQuality(BaseModel):
    status: DataStatus
    source: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class TechnicalSnapshot(BaseModel):
    close: Optional[float] = None
    ema20: Optional[float] = None
    ema60: Optional[float] = None
    ma50: Optional[float] = None
    ma200: Optional[float] = None
    rsi14: Optional[float] = None
    macd: Optional[float] = None
    macdSignal: Optional[float] = None
    macdHist: Optional[float] = None
    volume: Optional[float] = None
    vol20: Optional[float] = None
    volumeRatio: Optional[float] = None
    atr14: Optional[float] = None


class VNMarketContext(BaseModel):
    marketBias: MarketBias = "neutral"
    vnindexClose: Optional[float] = None
    vnindexChangePct: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)
    dataQuality: Dict[str, DataQuality] = Field(default_factory=dict)


class NewsSourceStatus(BaseModel):
    name: str
    status: Literal["available", "partial", "missing_tool", "failed", "disabled"] = "available"
    items: int = 0
    route: Optional[str] = None
    warning: Optional[str] = None


class NewsItem(BaseModel):
    title: str
    source: str = "public web"
    date: Optional[str] = None
    url: Optional[str] = None
    impact: Literal["high", "medium", "low"] = "medium"
    tone: Literal["positive", "neutral", "negative", "mixed", "unknown"] = "unknown"
    summary: str = ""
    sourceRoute: Optional[str] = None


class NewsCatalyst(BaseModel):
    checked: bool = False
    source: str = "agent-reach"
    checkedAt: Optional[str] = None
    freshnessWindow: str = "7d"
    sentiment: Literal["positive", "neutral", "negative", "mixed", "unknown"] = "unknown"
    catalysts: List[NewsItem] = Field(default_factory=list)
    sourcesChecked: List[NewsSourceStatus] = Field(default_factory=list)
    riskFlags: List[str] = Field(default_factory=list)
    dataQuality: DataQuality = Field(default_factory=lambda: DataQuality(status="missing", source="agent-reach"))


class VNActionPlan(BaseModel):
    ticker: str
    action: VNAction
    score: int
    confidence: float
    buyZone: Optional[Tuple[float, float]] = None
    breakoutTrigger: Optional[float] = None
    stopLoss: Optional[float] = None
    targets: List[float] = Field(default_factory=list)
    positionSizePct: Optional[int] = None
    reasons: List[str] = Field(default_factory=list)
    riskFlags: List[str] = Field(default_factory=list)
    dataQuality: Dict[str, DataQuality] = Field(default_factory=dict)
    technical: Optional[TechnicalSnapshot] = None
    newsCatalyst: Optional[NewsCatalyst] = None
