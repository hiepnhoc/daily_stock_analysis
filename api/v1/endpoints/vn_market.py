# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator, model_validator

from src.vn.services import vn_market_service
from src.services.vn_tplus_alerts import bootstrap_vn_tplus_rules, check_vn_tplus_watchlist

router = APIRouter()


class VNScanRequest(BaseModel):
    watchlist: List[str] = Field(default_factory=list)
    mode: Literal["tplus", "breakout", "pullback"] = "tplus"


class VNPortfolioHolding(BaseModel):
    ticker: str
    quantity: int = Field(gt=0)
    avgCost: float = Field(gt=0)
    sellableQty: int = Field(ge=0)
    pendingQty: int = Field(ge=0)

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, value: str) -> str:
        symbol = value.strip().upper()
        if len(symbol) != 3 or not symbol.isalpha() or not symbol.isascii():
            raise ValueError("Mã cổ phiếu phải gồm đúng 3 chữ cái A-Z")
        return symbol

    @model_validator(mode="after")
    def validate_quantities(self):
        if self.sellableQty + self.pendingQty > self.quantity:
            raise ValueError("Tổng khả dụng và chờ về không được vượt số lượng")
        return self


class VNPortfolioCheckRequest(BaseModel):
    holdings: List[VNPortfolioHolding] = Field(default_factory=list)
    includeNews: bool = False


class VNJournalCreateRequest(BaseModel):
    ticker: str
    action: str = "watch"
    score: int = 0
    note: str = ""


class VNDailyPlaybookRequest(BaseModel):
    watchlist: List[str] = Field(default_factory=list)
    holdings: List[VNPortfolioHolding] = Field(default_factory=list)
    mode: Literal["tplus", "breakout", "pullback"] = "tplus"


class VNAlertRule(BaseModel):
    id: str = ""
    ticker: str
    condition: str
    threshold: float = 0
    enabled: bool = True
    note: str = ""


class VNAlertRulesRequest(BaseModel):
    rules: List[VNAlertRule] = Field(default_factory=list)


class VNIntradayWatchRequest(BaseModel):
    watchlist: List[str] = Field(default_factory=list, max_length=50)
    cooldownSeconds: int = Field(default=900, ge=0, le=86400)

    @field_validator("watchlist")
    @classmethod
    def validate_watchlist(cls, values: List[str]) -> List[str]:
        output: List[str] = []
        for value in values:
            symbol = value.strip().upper()
            if len(symbol) != 3 or not symbol.isalpha() or not symbol.isascii():
                raise ValueError("Mỗi mã theo dõi phải gồm đúng 3 chữ cái A-Z")
            if symbol not in output:
                output.append(symbol)
        return output


@router.get("/market-overview")
def get_market_overview():
    return vn_market_service.get_market_overview()


@router.get("/readiness")
def readiness():
    return {"status": "ready", "service": "vn-market"}


@router.get("/providers")
def providers():
    """Expose secret-safe VN market-data provider diagnostics."""
    return vn_market_service.provider.get_provider_status()


@router.post("/scan")
def scan_watchlist(payload: VNScanRequest):
    return vn_market_service.scan_watchlist(payload.watchlist, mode=payload.mode)


@router.get("/analyze/{ticker}")
def analyze_ticker(ticker: str):
    return vn_market_service.analyze_ticker(ticker).model_dump(mode="json")


@router.get("/chart/{ticker}")
def ticker_chart(ticker: str, days: int = 160):
    return vn_market_service.ticker_chart(ticker, days=days)


@router.post("/portfolio-check")
def portfolio_check(payload: VNPortfolioCheckRequest):
    return vn_market_service.portfolio_check(
        [holding.model_dump() for holding in payload.holdings],
        include_news=payload.includeNews,
    )


@router.post("/sector-flow")
def sector_flow(payload: VNScanRequest):
    return vn_market_service.sector_flow(payload.watchlist, mode=payload.mode)


@router.post("/alerts/check")
def alerts_check(payload: VNScanRequest):
    return vn_market_service.alerts_check(payload.watchlist, mode=payload.mode)


@router.post("/alerts/rules/check")
def alert_rules_check(payload: VNAlertRulesRequest):
    return vn_market_service.alert_rules_check([rule.model_dump() for rule in payload.rules])


@router.post("/intraday-watch/check")
def intraday_watch_check(payload: VNIntradayWatchRequest):
    """Run a secret-safe live DNSE T+ check without writing alert history."""
    return check_vn_tplus_watchlist(payload.watchlist)


@router.post("/intraday-watch/bootstrap")
def intraday_watch_bootstrap(payload: VNIntradayWatchRequest):
    """Idempotently persist DNSE T+ rules in the shared Alert Center."""
    return bootstrap_vn_tplus_rules(payload.watchlist, cooldown_seconds=payload.cooldownSeconds)


@router.post("/journal")
def create_journal_signal(payload: VNJournalCreateRequest):
    return vn_market_service.create_journal_signal(payload.model_dump())


@router.get("/journal")
def list_journal_signals(limit: int = 100):
    return vn_market_service.list_journal_signals(limit=limit)


@router.post("/daily-playbook")
def daily_playbook(payload: VNDailyPlaybookRequest):
    return vn_market_service.daily_playbook(payload.watchlist, holdings=[holding.model_dump() for holding in payload.holdings], mode=payload.mode)


@router.post("/report")
def export_report(payload: VNScanRequest):
    return vn_market_service.export_report(payload.watchlist, mode=payload.mode)
