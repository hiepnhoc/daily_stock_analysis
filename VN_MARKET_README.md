# VN Market Web

Bản fork/local của `daily_stock_analysis` để thêm tab riêng cho thị trường Việt Nam.

## Path

```text
/Users/hiepln/github/hermes-agent/knowledge/daily_stock_analysis_vn
```

## Tính năng MVP đã có

- Frontend tab `/vn-market`.
- Backend namespace `/api/v1/vn/*`:
  - `GET /api/v1/vn/market-overview`
  - `POST /api/v1/vn/scan`
  - `GET /api/v1/vn/analyze/{ticker}`
  - `POST /api/v1/vn/report`
- VNDIRECT daily OHLCV fetcher.
- SSI iBoard breadth/live quote adapter best-effort.
- Indicator stack: EMA20, EMA60, MA50, MA200, RSI14, MACD, Vol20, ATR14.
- VN T+ ActionPlan: action, score, buy zone, breakout, stop, targets, size, reasons, risk flags.
- Analyze Stock VN panel for one-ticker action plan.
- Portfolio T+ panel: sellable/pending split, P/L, today plan, pending plan.
- Sector Flow panel: group watchlist by simple local sector map.
- Alerts VN panel: check stop/breakout/hot RSI/volume triggers.
- Journal / T+ Backtest panel: save/list signals for later T+3/T+5 review.
- HTML/JSON export to shared Hermes knowledge:

```text
/Users/hiepln/github/hermes-agent/knowledge/stock-reports/vn-market
```

## Chạy backend

```bash
cd /Users/hiepln/github/hermes-agent/knowledge/daily_stock_analysis_vn
.venv/bin/python main.py --serve-only
```

Hoặc:

```bash
cd /Users/hiepln/github/hermes-agent/knowledge/daily_stock_analysis_vn
.venv/bin/python -m uvicorn server:app --reload --host 127.0.0.1 --port 8000
```

## Chạy frontend dev

```bash
cd /Users/hiepln/github/hermes-agent/knowledge/daily_stock_analysis_vn/apps/dsa-web
npm run dev
```

Mở route:

```text
/vn-market
```

## Verify

Backend tests:

```bash
cd /Users/hiepln/github/hermes-agent/knowledge/daily_stock_analysis_vn
.venv/bin/python -m pytest tests/test_vn_market_mvp.py -q
```

Frontend build:

```bash
cd /Users/hiepln/github/hermes-agent/knowledge/daily_stock_analysis_vn/apps/dsa-web
npm run build
```

## Lưu ý

- Node hiện tại có warning engine vì `node v22.0.0`, trong khi Vite/jsdom muốn `>=22.12` hoặc `20.19+`. Build vẫn pass, nhưng nên nâng Node nếu muốn sạch warning.
- News/catalyst chưa được tích hợp, nên action plan luôn có risk flag `chưa kiểm chứng news/catalyst`.
- Sector flow và Portfolio/T+ assistant là phase sau.
