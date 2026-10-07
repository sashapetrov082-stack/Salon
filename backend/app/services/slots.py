"""Расчёт свободных слотов.

Только чистые функции: на вход — расписание и занятость, на выход — слоты.
Загрузка данных из БД — в services/availability.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class WeeklyInterval:
    weekday: int  # 0=пн..6=вс
    start: time
    end: time


@dataclass(frozen=True)
class OverrideInterval:
    date: date
    is_day_off: bool
    start: time | None = None
    end: time | None = None


@dataclass(frozen=True)
class Busy:
    """Занятый интервал [start, end) в абсолютном времени (aware datetime)."""

    start: datetime
    end: datetime


@dataclass(frozen=True)
class FreeInterval:
    start: datetime
    end: datetime
    ends_at_shift_end: bool


@dataclass
class StaffSchedule:
    """Всё, что нужно знать о мастере для расчёта слотов на диапазон дат."""

    staff_id: int
    weekly: list[WeeklyInterval] = field(default_factory=list)
    breaks: list[WeeklyInterval] = field(default_factory=list)
    overrides: list[OverrideInterval] = field(default_factory=list)
    busy: list[Busy] = field(default_factory=list)  # time_off + активные записи
    sort_order: int = 0
    # число активных записей по датам (для выбора мастера в режиме «любой»)
    appointments_per_day: dict[date, int] = field(default_factory=dict)


@dataclass(frozen=True)
class SlotRules:
    step_min: int
    min_lead_time_min: int
    horizon_days: int
    tz: ZoneInfo


@dataclass(frozen=True)
class Slot:
    starts_at: datetime  # aware, в часовом поясе салона
    staff_id: int


def _local_dt(day: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, t, tzinfo=tz)


def _end_dt(day: date, t: time, tz: ZoneInfo) -> datetime:
    # 00:00 в качестве конца интервала означает полночь следующего дня
    if t == time(0, 0):
        return datetime.combine(day + timedelta(days=1), t, tzinfo=tz)
    return datetime.combine(day, t, tzinfo=tz)


def work_intervals_for_day(
    day: date,
    weekly: Iterable[WeeklyInterval],
    overrides: Iterable[OverrideInterval],
) -> list[tuple[time, time]]:
    """Шаг 1: рабочие интервалы на дату (override целиком заменяет шаблон)."""
    day_overrides = [o for o in overrides if o.date == day]
    if day_overrides:
        if any(o.is_day_off for o in day_overrides):
            return []
        return sorted(
            (o.start, o.end) for o in day_overrides if o.start is not None and o.end is not None
        )
    wd = day.weekday()
    return sorted((w.start, w.end) for w in weekly if w.weekday == wd)


def _merge(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    result: list[tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            if end > result[-1][1]:
                result[-1] = (result[-1][0], end)
        else:
            result.append((start, end))
    return result


def _subtract(
    pieces: list[FreeInterval], cut_start: datetime, cut_end: datetime
) -> list[FreeInterval]:
    result: list[FreeInterval] = []
    for p in pieces:
        if cut_end <= p.start or cut_start >= p.end:
            result.append(p)
            continue
        if cut_start > p.start:
            result.append(FreeInterval(p.start, cut_start, ends_at_shift_end=False))
        if cut_end < p.end:
            result.append(FreeInterval(cut_end, p.end, p.ends_at_shift_end))
    return result


def free_intervals_for_day(
    day: date,
    tz: ZoneInfo,
    work: Sequence[tuple[time, time]],
    breaks: Iterable[WeeklyInterval],
    busy: Iterable[Busy],
) -> list[FreeInterval]:
    """Шаги 1–5: свободные интервалы мастера на дату."""
    shifts = _merge([(_local_dt(day, s, tz), _end_dt(day, e, tz)) for s, e in work])
    pieces = [FreeInterval(s, e, ends_at_shift_end=True) for s, e in shifts]
    if not pieces:
        return []
    wd = day.weekday()
    for b in breaks:
        if b.weekday == wd:
            pieces = _subtract(pieces, _local_dt(day, b.start, tz), _end_dt(day, b.end, tz))
    for item in busy:
        pieces = _subtract(pieces, item.start, item.end)
    return pieces


def _align_up(dt: datetime, day: date, step_min: int, tz: ZoneInfo) -> datetime:
    midnight = datetime.combine(day, time(0, 0), tzinfo=tz)
    minutes = (dt - midnight).total_seconds() / 60
    steps = -(-minutes // step_min)  # ceil
    return midnight + timedelta(minutes=int(steps) * step_min)


def slot_starts_in_interval(
    interval: FreeInterval,
    day: date,
    duration_min: int,
    buffer_min: int,
    step_min: int,
    tz: ZoneInfo,
) -> list[datetime]:
    duration = timedelta(minutes=duration_min)
    tail = timedelta(minutes=duration_min + buffer_min)
    starts: list[datetime] = []
    s = _align_up(interval.start, day, step_min, tz)
    step = timedelta(minutes=step_min)
    while s + duration <= interval.end:
        if s + tail <= interval.end or interval.ends_at_shift_end:
            starts.append(s)
        s += step
    return starts


def booking_window(now: datetime, rules: SlotRules) -> tuple[datetime, date]:
    """Самое раннее время начала и последний доступный день записи."""
    earliest = now + timedelta(minutes=rules.min_lead_time_min)
    today = now.astimezone(rules.tz).date()
    last_day = today + timedelta(days=rules.horizon_days - 1)
    return earliest, last_day


def staff_slots_for_day(
    schedule: StaffSchedule,
    day: date,
    duration_min: int,
    buffer_min: int,
    rules: SlotRules,
    now: datetime,
    *,
    enforce_window: bool = True,
) -> list[datetime]:
    if enforce_window:
        earliest, last_day = booking_window(now, rules)
        if day > last_day or day < now.astimezone(rules.tz).date():
            return []
    work = work_intervals_for_day(day, schedule.weekly, schedule.overrides)
    free = free_intervals_for_day(day, rules.tz, work, schedule.breaks, schedule.busy)
    starts: list[datetime] = []
    for interval in free:
        starts.extend(
            slot_starts_in_interval(
                interval, day, duration_min, buffer_min, rules.step_min, rules.tz
            )
        )
    if enforce_window:
        starts = [s for s in starts if s >= earliest]
    return sorted(set(starts))


def pick_staff(candidates: Sequence[StaffSchedule], day: date) -> StaffSchedule:
    """Режим «любой мастер»: меньше всего записей в этот день, затем sort_order."""
    return min(
        candidates,
        key=lambda s: (s.appointments_per_day.get(day, 0), s.sort_order, s.staff_id),
    )


@dataclass(frozen=True)
class ServiceParams:
    duration_min: int
    buffer_min: int


def slots_for_day(
    schedules: Sequence[StaffSchedule],
    params: Mapping[int, ServiceParams],
    day: date,
    rules: SlotRules,
    now: datetime,
) -> list[Slot]:
    """Слоты на дату для одного мастера или объединение по нескольким («любой»).

    Для каждого времени возвращается мастер, которого выберет бронирование.
    """
    by_time: dict[datetime, list[StaffSchedule]] = {}
    for sched in schedules:
        p = params[sched.staff_id]
        for s in staff_slots_for_day(sched, day, p.duration_min, p.buffer_min, rules, now):
            by_time.setdefault(s, []).append(sched)
    return [
        Slot(starts_at=t, staff_id=pick_staff(by_time[t], day).staff_id) for t in sorted(by_time)
    ]


def days_with_slots(
    schedules: Sequence[StaffSchedule],
    params: Mapping[int, ServiceParams],
    days: Iterable[date],
    rules: SlotRules,
    now: datetime,
) -> dict[date, bool]:
    result: dict[date, bool] = {}
    for day in days:
        result[day] = any(
            staff_slots_for_day(
                s, day, params[s.staff_id].duration_min, params[s.staff_id].buffer_min, rules, now
            )
            for s in schedules
        )
    return result


def nearest_slot(
    schedule: StaffSchedule,
    duration_min: int,
    buffer_min: int,
    rules: SlotRules,
    now: datetime,
    horizon_days: int = 14,
) -> datetime | None:
    """Первый подходящий слот мастера в пределах horizon_days (и горизонта записи)."""
    today = now.astimezone(rules.tz).date()
    for i in range(min(horizon_days, rules.horizon_days)):
        starts = staff_slots_for_day(
            schedule, today + timedelta(days=i), duration_min, buffer_min, rules, now
        )
        if starts:
            return starts[0]
    return None


def is_slot_available(
    schedule: StaffSchedule,
    starts_at: datetime,
    duration_min: int,
    buffer_min: int,
    rules: SlotRules,
    now: datetime,
) -> bool:
    day = starts_at.astimezone(rules.tz).date()
    return starts_at.astimezone(UTC) in {
        s.astimezone(UTC)
        for s in staff_slots_for_day(schedule, day, duration_min, buffer_min, rules, now)
    }
