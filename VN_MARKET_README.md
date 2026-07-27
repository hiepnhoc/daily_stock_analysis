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
- DNSE OpenAPI read-only adapter (daily/intraday OHLC REST, latest trade, native WebSocket protocol) làm primary khi có key.
- SSI FastConnect API v3 read-only adapter giữ vai trò fallback OHLCV/breadth; VNDIRECT/iBoard là fallback cuối; trading/execution luôn disabled.
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

## Cấu hình DNSE OpenAPI

DNSE là primary cho OHLCV/latest trade khi đủ key. Integration chỉ dùng **Market Data read-only**; không gọi account, OTP, trading-token hay order endpoint.

```bash
VN_MARKET_DATA_PROVIDER=auto
DNSE_API_KEY=...
DNSE_API_SECRET=...
VN_DNSE_PRICE_UNIT=thousand_vnd
```

- `auto`: DNSE → SSI FastConnect nếu có key → VNDIRECT.
- `dnse` hoặc `dnse_openapi`: ép thử DNSE trước nhưng vẫn fail-soft qua SSI/VNDIRECT.
- `ssi_fastconnect`: bỏ qua DNSE và dùng SSI → VNDIRECT.
- `vndirect`: chỉ dùng VNDIRECT cho OHLCV.
- Breadth chưa có contract tổng hợp từ DNSE nên tiếp tục dùng SSI FastConnect hoặc SSI iBoard.
- `VN_DNSE_PRICE_UNIT`: `thousand_vnd` hoặc `vnd`; không đoán đơn vị theo magnitude.
- REST adapter gọi trực tiếp `/price/ohlc` và `/price/{symbol}/trades/latest` bằng HMAC-SHA256.
- WebSocket dùng native protocol theo tài liệu DNSE hiện tại, hỗ trợ tick, quote 3 mức giá và OHLC 1m. Không dùng stream runner của `dnse==0.5.0` vì package đang gửi sai kiểu `nonce` và thiếu subscribe envelope so với live server.

Kiểm tra trạng thái:

```bash
.venv/bin/python scripts/smoke_dnse_openapi.py --status-only
curl http://127.0.0.1:8000/api/v1/vn/providers
```

Sau khi điền key, smoke REST:

```bash
.venv/bin/python scripts/smoke_dnse_openapi.py --ticker HPG --days 5
```

Smoke REST + WebSocket 30 giây:

```bash
.venv/bin/python scripts/smoke_dnse_openapi.py --ticker HPG --days 5 --stream-seconds 30
```

### DNSE intraday T+ watcher

Watcher sử dụng ActionPlan trên nến hoàn tất và DNSE latest trade để kiểm tra mỗi phút:

- vào vùng mua nhưng vẫn đạt R:R tối thiểu;
- breakout có volume xác nhận;
- chạm stop/target;
- volume/Vol20 spike;
- anti-FOMO khi vượt `buy_high` nhưng R:R T1 dưới 1,2.

```bash
AGENT_EVENT_MONITOR_ENABLED=true
AGENT_EVENT_MONITOR_INTERVAL_MINUTES=1
```

API:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/vn/intraday-watch/bootstrap \
  -H 'Content-Type: application/json' \
  -d '{"watchlist":["HPG","FPT","SSI"],"cooldownSeconds":900}'

curl -X POST http://127.0.0.1:8000/api/v1/vn/intraday-watch/check \
  -H 'Content-Type: application/json' \
  -d '{"watchlist":["HPG","FPT","SSI"]}'
```

Web: mở **VN Market → Cảnh báo & Nhật ký**, bấm **Bật DNSE watcher**. Bootstrap là idempotent; mỗi signal/ticker chỉ ghi một trigger mỗi ngày để không spam khi chưa cấu hình notification channel. Alert Center vẫn lưu trigger cục bộ ngay cả khi Telegram/Discord/Webhook chưa được cấu hình.

Hiện worker production là polling 1 phút bằng latest-trade REST. Native WebSocket vẫn dùng cho bounded stream/smoke; reconnect/gap/out-of-order metrics phải được soak-test trước khi thay polling bằng collector liên tục.

## Cấu hình SSI FastConnect v3 fallback

SSI integration vẫn chỉ dùng **Market Data read-only**; không có private key, OTP, account hay order endpoint.

```bash
VN_MARKET_DATA_PROVIDER=auto
SSI_FASTCONNECT_CLIENT_ID=...
SSI_FASTCONNECT_API_KEY=...
SSI_FASTCONNECT_API_SECRET=...
VN_SSI_PRICE_UNIT=thousand_vnd
```

- `auto`: SSI chỉ đứng sau DNSE cho OHLCV khi cả hai có key; SSI vẫn được ưu tiên cho breadth vì DNSE chưa có contract breadth tổng hợp.
- `ssi_fastconnect`: ép SSI làm OHLCV primary và fail-soft về VNDIRECT.
- `vndirect`: bỏ qua cả DNSE/SSI cho OHLCV.
- `VN_SSI_PRICE_UNIT` phải khai báo đúng contract key: `thousand_vnd` hoặc `vnd`; hệ thống không đoán đơn vị theo độ lớn giá.
- Token chỉ cache trong RAM của process, không ghi xuống repository hoặc `token_cache.json`.

Kiểm tra trạng thái không lộ secrets:

```bash
.venv/bin/python scripts/smoke_ssi_fastconnect.py --status-only
curl http://127.0.0.1:8000/api/v1/vn/providers
```

Sau khi điền key, chạy authenticated smoke test:

```bash
.venv/bin/python scripts/smoke_ssi_fastconnect.py --ticker HPG --days 5
```

Kết quả smoke gồm số bars, bar mới nhất, VNINDEX summary và rate-limit headers nếu SSI trả về. Không commit file `.env`.

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

- `/usr/local/bin/node` hiện là v22.0.0, thấp hơn yêu cầu của Vite/jsdom. Dùng Homebrew Node 26 (`PATH="/opt/homebrew/opt/node/bin:$PATH"`) cho frontend test/build sạch engine warning.
- News/catalyst là evidence best-effort, không tự động biến thành lệnh mua/bán; một nguồn hỏng không chặn technical/portfolio.
- Sector flow hiện vẫn dùng mapping ngành cục bộ; bước tiếp theo là taxonomy/provider ngành và portfolio risk theo sector/liquidity.
