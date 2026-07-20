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
- Persistent portfolio ledger `/portfolio` hỗ trợ account `market=vn`, `baseCurrency=VND`, cash/trade/corporate action/NAV/P&L và snapshot FIFO/AVG.
- Buy lot VN có `settlement_date` T+2 theo lịch giao dịch versioned. Calendar 2026 bỏ qua cuối tuần và các kỳ nghỉ chính thức HOSE/HNX, trả `settlement_estimated=false`; năm chưa có coverage dùng weekday fallback và giữ `settlement_estimated=true`.
- `/portfolio` có template import `generic_vn` cho CSV tiếng Việt chung, hỗ trợ UTF-8 BOM/CP1258, ngày `dd/mm/yyyy`, số định dạng Việt Nam, preview/dedup/account-market guard và settlement metadata. Người dùng phải chọn rõ giá là VND thực hay nghìn VND; template không tuyên bố tương thích format riêng SSI/VPS/TCBS/VNDIRECT.
- Risk report kết hợp sellable/pending T+, sector taxonomy dùng chung và GTGD gần đây để cảnh báo tỷ trọng hàng chờ về, dữ liệu thanh khoản thiếu hoặc số phiên thoát lệnh ước tính cao. Card **T+ inventory & liquidity** chỉ hỗ trợ quyết định, không tự phát lệnh.
- Nút **Nhập vị thế mở đầu vào sổ** trên `/vn-portfolio` tạo opening lots không tác động cash; chỉ áp dụng cho account VN chưa có trade để tránh cộng trùng.
- Nút **Tải từ sổ VN** đưa snapshot persistent trở lại Portfolio T+ decision-support; localStorage chỉ là scratchpad tạm.
- Sector Flow panel: group watchlist by simple local sector map.
- Alerts VN panel: check stop/breakout/hot RSI/volume triggers.
- Journal / T+ Backtest panel: save/list signals for later T+3/T+5 review.
- Agent Reach news/catalyst cho Analyze và explicit Portfolio check:
  - Google News RSS, direct VN RSS, Jina Reader và Exa qua `mcporter`, chạy song song theo nguồn;
  - cache TTL mặc định 15 phút;
  - fail-open, giữ source/route/link gốc và trạng thái từng nguồn.
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
/vn-portfolio
/portfolio
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

## Cấu hình news/catalyst

```bash
# Bật/tắt toàn bộ pipeline (mặc định: bật)
VN_NEWS_CATALYST_ENABLED=1

# Cache theo ticker + cửa sổ ngày, đơn vị giây (mặc định: 900)
VN_NEWS_CACHE_TTL_SECONDS=900

# Tùy chọn khi backend service không có npm user bin trong PATH
VN_NEWS_MCPORTER_PATH="$HOME/.npm-global/bin/mcporter"
```

Analyze luôn kiểm tra news. Nút **Kiểm tra Portfolio** cũng lấy news/catalyst; auto-refresh Portfolio giữ chế độ technical-only để tránh gọi mạng nền quá dày.

## Lưu ý

- Node hiện tại có warning engine vì `node v22.0.0`, trong khi Vite/jsdom muốn `>=22.12` hoặc `20.19+`. Build vẫn pass, nhưng nên nâng Node nếu muốn sạch warning.
- News/catalyst là evidence best-effort, không tự động biến thành lệnh mua/bán; một nguồn hỏng không chặn technical/portfolio.
- Sector flow hiện vẫn dùng mapping ngành cục bộ; bước tiếp theo là taxonomy/provider ngành và portfolio risk theo sector/liquidity.
