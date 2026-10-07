from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.services.slots import (
    Busy,
    OverrideInterval,
    ServiceParams,
    SlotRules,
    StaffSchedule,
    WeeklyInterval,
    days_with_slots,
    is_slot_available,
    nearest_slot,
    pick_staff,
    slots_for_day,
    staff_slots_for_day,
    work_intervals_for_day,
)

TZ = ZoneInfo("Europe/Moscow")
DAY = date(2026, 10, 12)  # понедельник
WD = DAY.weekday()
# «сейчас» — за неделю до дня записи, чтобы не мешал min_lead_time
NOW = datetime(2026, 10, 5, 8, 0, tzinfo=TZ)
RULES = SlotRules(step_min=15, min_lead_time_min=60, horizon_days=30, tz=TZ)


def t(h: int, m: int = 0) -> time:
    return time(h, m)


def at(h: int, m: int = 0, day: date = DAY) -> datetime:
    return datetime.combine(day, time(h, m), tzinfo=TZ)


def hm(slots: list[datetime]) -> list[str]:
    return [s.strftime("%H:%M") for s in slots]


def sched(**kw: object) -> StaffSchedule:
    base: dict[str, object] = {
        "staff_id": 1,
        "weekly": [WeeklyInterval(WD, t(10), t(14))],
    }
    base.update(kw)
    return StaffSchedule(**base)  # type: ignore[arg-type]


def test_simple_shift_grid() -> None:
    slots = staff_slots_for_day(sched(), DAY, 60, 0, RULES, NOW)
    assert hm(slots)[0] == "10:00"
    assert hm(slots)[-1] == "13:00"
    assert len(slots) == 13


def test_shift_with_break() -> None:
    s = sched(
        weekly=[WeeklyInterval(WD, t(10), t(18))],
        breaks=[WeeklyInterval(WD, t(13), t(14))],
    )
    slots = hm(staff_slots_for_day(s, DAY, 60, 0, RULES, NOW))
    assert "12:00" in slots
    assert "12:15" not in slots  # закончилась бы в перерыве
    assert "13:00" not in slots and "13:45" not in slots
    assert "14:00" in slots
    assert slots[-1] == "17:00"


def test_split_shift_rows() -> None:
    s = sched(weekly=[WeeklyInterval(WD, t(10), t(12)), WeeklyInterval(WD, t(15), t(17))])
    slots = hm(staff_slots_for_day(s, DAY, 60, 0, RULES, NOW))
    assert slots[:5] == ["10:00", "10:15", "10:30", "10:45", "11:00"]
    assert "11:15" not in slots and "14:45" not in slots
    assert slots[-1] == "16:00"


def test_appointment_with_buffer_blocks_time() -> None:
    # существующая запись 11:00–12:00 + буфер 15 → занято до 12:15
    s = sched(busy=[Busy(at(11), at(12, 15))])
    slots = hm(staff_slots_for_day(s, DAY, 60, 15, RULES, NOW))
    # новая услуга 60 мин + 15 буфер должна закончиться до 11:00
    assert "09:45" not in slots
    assert "10:00" not in slots  # 10:00+60+15 = 11:15 > 11:00
    assert "12:15" in slots
    assert "12:00" not in slots


def test_buffer_required_before_next_busy() -> None:
    s = sched(busy=[Busy(at(12), at(13))])
    slots = hm(staff_slots_for_day(s, DAY, 60, 30, RULES, NOW))
    assert "10:30" in slots  # 10:30 + 90 = 12:00
    assert "10:45" not in slots


def test_service_does_not_fit_remaining_shift() -> None:
    s = sched(weekly=[WeeklyInterval(WD, t(10), t(11, 30))])
    assert staff_slots_for_day(s, DAY, 120, 0, RULES, NOW) == []
    slots = hm(staff_slots_for_day(s, DAY, 90, 0, RULES, NOW))
    assert slots == ["10:00"]


def test_last_slot_of_shift_without_buffer() -> None:
    # услуга 60 мин, буфер 30; смена до 14:00 → 13:00 допустимо (буфер в конце не нужен)
    slots = hm(staff_slots_for_day(sched(), DAY, 60, 30, RULES, NOW))
    assert slots[-1] == "13:00"
    assert "12:45" in slots


def test_buffer_needed_before_break_not_only_shift_end() -> None:
    s = sched(breaks=[WeeklyInterval(WD, t(12), t(13))])
    slots = hm(staff_slots_for_day(s, DAY, 60, 30, RULES, NOW))
    assert "10:30" in slots
    assert "11:00" not in slots  # перед перерывом буфер нужен
    assert slots[-1] == "13:00"


def test_override_day_off() -> None:
    s = sched(overrides=[OverrideInterval(DAY, is_day_off=True)])
    assert staff_slots_for_day(s, DAY, 30, 0, RULES, NOW) == []


def test_override_replaces_template() -> None:
    s = sched(
        overrides=[
            OverrideInterval(DAY, False, t(15), t(16)),
            OverrideInterval(DAY, False, t(18), t(19)),
        ]
    )
    slots = hm(staff_slots_for_day(s, DAY, 60, 0, RULES, NOW))
    assert slots == ["15:00", "18:00"]


def test_override_on_day_without_template() -> None:
    sunday = DAY + timedelta(days=6)
    s = sched(overrides=[OverrideInterval(sunday, False, t(10), t(11))])
    assert hm(staff_slots_for_day(s, sunday, 60, 0, RULES, NOW)) == ["10:00"]
    assert work_intervals_for_day(sunday, s.weekly, []) == []


def test_time_off_part_of_day() -> None:
    s = sched(busy=[Busy(at(11), at(12, 30))])
    slots = hm(staff_slots_for_day(s, DAY, 30, 0, RULES, NOW))
    assert "10:30" in slots
    assert "10:45" not in slots
    assert "12:15" not in slots
    assert "12:30" in slots


def test_time_off_whole_day_across_midnight() -> None:
    s = sched(busy=[Busy(at(0) - timedelta(days=1), at(0) + timedelta(days=2))])
    assert staff_slots_for_day(s, DAY, 30, 0, RULES, NOW) == []


def test_non_standard_shift_start_aligns_to_grid() -> None:
    s = sched(weekly=[WeeklyInterval(WD, t(9, 10), t(12))])
    slots = hm(staff_slots_for_day(s, DAY, 30, 0, RULES, NOW))
    assert slots[0] == "09:15"


def test_grid_after_busy_end_off_grid() -> None:
    s = sched(busy=[Busy(at(10), at(10, 50))])
    slots = hm(staff_slots_for_day(s, DAY, 30, 0, RULES, NOW))
    assert slots[0] == "11:00"


def test_min_lead_time_filter() -> None:
    now = at(10, 20)
    slots = hm(staff_slots_for_day(sched(), DAY, 30, 0, RULES, now))
    # раньше 11:20 нельзя
    assert slots[0] == "11:30"


def test_past_day_and_horizon() -> None:
    assert staff_slots_for_day(sched(), DAY, 30, 0, RULES, at(10) + timedelta(days=1)) == []
    rules = SlotRules(step_min=15, min_lead_time_min=60, horizon_days=3, tz=TZ)
    assert staff_slots_for_day(sched(), DAY, 30, 0, rules, NOW) == []
    now = at(7) - timedelta(days=2)
    assert staff_slots_for_day(sched(), DAY, 30, 0, rules, now) != []


def test_any_master_union_and_pick() -> None:
    a = StaffSchedule(
        staff_id=1,
        weekly=[WeeklyInterval(WD, t(10), t(12))],
        sort_order=2,
        appointments_per_day={DAY: 1},
    )
    b = StaffSchedule(
        staff_id=2,
        weekly=[WeeklyInterval(WD, t(11), t(13))],
        sort_order=1,
        appointments_per_day={DAY: 3},
    )
    params = {1: ServiceParams(60, 0), 2: ServiceParams(60, 0)}
    slots = slots_for_day([a, b], params, DAY, RULES, NOW)
    times = [s.starts_at.strftime("%H:%M") for s in slots]
    assert times == sorted(set(times))
    assert times[0] == "10:00" and times[-1] == "12:00"
    by_time = {s.starts_at.strftime("%H:%M"): s.staff_id for s in slots}
    assert by_time["10:00"] == 1  # только a
    assert by_time["12:00"] == 2  # только b
    assert by_time["11:00"] == 1  # оба свободны, у a меньше записей


def test_any_master_tie_breaks_by_sort_order() -> None:
    a = StaffSchedule(staff_id=1, sort_order=5)
    b = StaffSchedule(staff_id=2, sort_order=1)
    assert pick_staff([a, b], DAY).staff_id == 2


def test_any_master_with_staff_specific_duration() -> None:
    a = StaffSchedule(staff_id=1, weekly=[WeeklyInterval(WD, t(10), t(11))])
    b = StaffSchedule(staff_id=2, weekly=[WeeklyInterval(WD, t(10), t(11))])
    params = {1: ServiceParams(60, 0), 2: ServiceParams(30, 0)}
    slots = slots_for_day([a, b], params, DAY, RULES, NOW)
    by_time = {s.starts_at.strftime("%H:%M"): s.staff_id for s in slots}
    assert by_time == {"10:00": 1, "10:15": 2, "10:30": 2}


def test_days_with_slots_and_nearest() -> None:
    s = sched()
    days = [DAY + timedelta(days=i) for i in range(8)]
    result = days_with_slots([s], {1: ServiceParams(60, 0)}, days, RULES, NOW)
    assert result[DAY] is True
    assert result[DAY + timedelta(days=1)] is False
    assert result[DAY + timedelta(days=7)] is True
    assert nearest_slot(s, 60, 0, RULES, NOW) == at(10, day=NOW.date())  # тоже понедельник
    assert nearest_slot(StaffSchedule(staff_id=9), 60, 0, RULES, NOW) is None


def test_is_slot_available() -> None:
    s = sched(busy=[Busy(at(11), at(12))])
    assert is_slot_available(s, at(10), 60, 0, RULES, NOW)
    assert not is_slot_available(s, at(10, 30), 60, 0, RULES, NOW)
    assert not is_slot_available(s, at(10, 5), 30, 0, RULES, NOW)  # не на сетке
    assert is_slot_available(s, at(12).astimezone(ZoneInfo("UTC")), 60, 0, RULES, NOW)


def test_shift_until_midnight() -> None:
    s = sched(weekly=[WeeklyInterval(WD, t(22), t(0))])
    assert hm(staff_slots_for_day(s, DAY, 60, 0, RULES, NOW)) == [
        "22:00",
        "22:15",
        "22:30",
        "22:45",
        "23:00",
    ]
