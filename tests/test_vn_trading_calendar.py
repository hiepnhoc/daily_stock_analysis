from datetime import date

from src.vn.trading_calendar import add_vn_trading_days, vn_settlement_info


def test_2026_hose_holiday_calendar_skips_30_april_and_1_may() -> None:
    result = vn_settlement_info(date(2026, 4, 29), trading_days=2)

    assert result.settlement_date == date(2026, 5, 5)
    assert result.estimated is False
    assert result.calendar_version == "hose-hnx-2026-v1"


def test_known_calendar_marks_holidays_as_closed() -> None:
    assert add_vn_trading_days(date(2026, 2, 13), 1).settlement_date == date(2026, 2, 23)
    assert add_vn_trading_days(date(2026, 8, 28), 1).settlement_date == date(2026, 9, 3)
    for exchange in ("hose", "hnx", "upcom"):
        assert add_vn_trading_days(date(2026, 4, 29), 2, exchange=exchange).settlement_date == date(2026, 5, 5)


def test_unknown_year_falls_back_to_weekdays_and_marks_estimated() -> None:
    result = vn_settlement_info(date(2027, 1, 8), trading_days=2)

    assert result.settlement_date == date(2027, 1, 12)
    assert result.estimated is True
    assert result.calendar_version == "weekday-fallback"
