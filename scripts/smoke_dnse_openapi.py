#!/usr/bin/env python3
"""Secret-safe DNSE OpenAPI read-only REST/WebSocket smoke test."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.vn.data import dnse_openapi  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test DNSE OpenAPI market data")
    parser.add_argument("--ticker", default="HPG")
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument("--status-only", action="store_true")
    parser.add_argument("--stream-seconds", type=int, default=0)
    args = parser.parse_args()

    status = dnse_openapi.get_status()
    output: dict = {"status": status}
    if args.status_only:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    if not status["configured"]:
        output["error"] = "dnse_credentials_not_configured"
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 2

    symbol = args.ticker.strip().upper()
    try:
        frame = dnse_openapi.fetch_daily_bars(symbol, days=max(1, args.days))
        latest_trade = dnse_openapi.fetch_latest_trade(symbol)
        output.update(
            {
                "ticker": symbol,
                "bars": len(frame),
                "latestBar": frame.iloc[-1].to_dict() if not frame.empty else None,
                "latestTrade": latest_trade,
                "rateLimit": frame.attrs.get("rate_limit"),
            }
        )
        if args.stream_seconds > 0:
            output["stream"] = asyncio.run(
                dnse_openapi.capture_market_stream(
                    symbol,
                    seconds=min(max(args.stream_seconds, 1), 120),
                )
            )
    except Exception as exc:
        output["error"] = type(exc).__name__
        output["message"] = str(exc)[:300]
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
        return 1

    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    rest_ok = bool(output.get("latestBar") and output.get("latestTrade"))
    stream_ok = args.stream_seconds <= 0 or bool(output.get("stream", {}).get("ok"))
    return 0 if rest_ok and stream_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
