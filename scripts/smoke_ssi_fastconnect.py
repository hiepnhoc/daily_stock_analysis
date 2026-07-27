#!/usr/bin/env python3
"""Secret-safe SSI FastConnect v3 read-only smoke test."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.vn.data import ssi_fastconnect  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test SSI FastConnect v3 market data")
    parser.add_argument("--ticker", default="HPG", help="VN ticker/index used for daily OHLC smoke")
    parser.add_argument("--days", type=int, default=5, help="Number of daily bars to request")
    parser.add_argument("--status-only", action="store_true", help="Only print secret-safe configuration status")
    args = parser.parse_args()

    status = ssi_fastconnect.get_status()
    output: dict = {"status": status}
    if args.status_only:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    if not status["configured"]:
        output["error"] = "ssi_fastconnect_credentials_not_configured"
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 2

    try:
        frame = ssi_fastconnect.fetch_daily_bars(args.ticker, days=max(args.days, 1))
        summary = ssi_fastconnect.fetch_index_summary("VNINDEX")
    except Exception as exc:  # smoke CLI must return a compact, secret-safe failure
        output["error"] = type(exc).__name__
        output["message"] = str(exc)[:300]
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 1

    latest = frame.iloc[-1].to_dict() if not frame.empty else None
    output.update(
        {
            "ticker": args.ticker.strip().upper(),
            "bars": len(frame),
            "latest": latest,
            "rateLimit": frame.attrs.get("rate_limit"),
            "indexSummary": summary,
        }
    )
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    return 0 if latest and summary else 1


if __name__ == "__main__":
    raise SystemExit(main())
