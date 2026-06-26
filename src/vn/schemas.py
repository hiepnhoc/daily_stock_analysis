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
