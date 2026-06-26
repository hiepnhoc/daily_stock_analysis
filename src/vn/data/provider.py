# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd

from src.vn.data import vndirect


def get_daily_bars(ticker: str, days: int = 260) -> pd.DataFrame:
    """Return VN daily bars using local VN source first.

    This facade exists so tests and future providers can patch one place.
    """
    return vndirect.fetch_ohlcv(ticker, days=days)
