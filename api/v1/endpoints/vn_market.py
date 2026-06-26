# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.vn.services import vn_market_service

router = APIRouter()


class VNScanRequest(BaseModel):
    watchlist: List[str] = Field(default_factory=list)
    mode: Literal["tplus", "breakout", "pullback"] = "tplus"


class VNPortfolioHolding(BaseModel):
    ticker: str
    quantity: int = 0
    avgCost: float = 0
    sellableQty: int = 0
    pendingQty: int = 0


class VNPortfolioCheckRequest(BaseModel):
    holdings: List[VNPortfolioHolding] = Field(default_factory=list)


@router.get("/market-overview")
def get_market_overview():
    return vn_market_service.get_market_overview()


@router.post("/scan")
def scan_watchlist(payload: VNScanRequest):
    return vn_market_service.scan_watchlist(payload.watchlist, mode=payload.mode)


@router.get("/analyze/{ticker}")
def analyze_ticker(ticker: str):
    return vn_market_service.analyze_ticker(ticker).model_dump(mode="json")


@router.post("/portfolio-check")
def portfolio_check(payload: VNPortfolioCheckRequest):
    return vn_market_service.portfolio_check([holding.model_dump() for holding in payload.holdings])


@router.post("/report")
def export_report(payload: VNScanRequest):
    return vn_market_service.export_report(payload.watchlist, mode=payload.mode)
