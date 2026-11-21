from app.routes.prescriptions_simple import _prescribed_quantity
from app.utils.prescription_schedule import (
    build_dosage_instruction,
    parse_duration_days,
    schedule_to_mar,
)


def test_parse_duration_days_expands_weeks_and_months():
    assert parse_duration_days("5 days") == 5
    assert parse_duration_days("5") == 5
    assert parse_duration_days("1 week") == 7
    assert parse_duration_days("2 weeks") == 14
    assert parse_duration_days("1 month") == 30
    assert parse_duration_days("2 months") == 60
    assert parse_duration_days("fortnight") == 14
    assert parse_duration_days("as directed") is None
    assert parse_duration_days("") is None


def test_every_n_hours_builds_mar_times_and_instructions():
    code, times = schedule_to_mar("q8h")
    assert code == "Q8H"
    assert times == ["08:00", "16:00", "00:00"]
    code6, times6 = schedule_to_mar("q6h")
    assert code6 == "Q6H"
    assert times6 == ["08:00", "14:00", "20:00", "02:00"]
    assert build_dosage_instruction("1 tab", "q8h", "after_food") == "1 tab - every 8 hours after food"
    assert schedule_to_mar("1-0-1")[0] == "BD"


def test_prescribed_quantity_keeps_decimals():
    assert _prescribed_quantity("2.5") == 2.5
    assert _prescribed_quantity("0.5") == 0.5
    assert _prescribed_quantity(".5 tab") == 0.5
    assert _prescribed_quantity("10 tablets") == 10
    assert _prescribed_quantity(None) == 1
