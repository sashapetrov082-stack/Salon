"""Загрузка расписаний из БД и вызов чистых функций slots.py."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError, NotFound
from app.models import (
    ACTIVE_STATUSES,
    Appointment,
    Salon,
    ScheduleBreak,
    ScheduleOverride,
    Service,
    Staff,
    StaffService,
    TimeOff,
    WorkSchedule,
)
from app.services import slots as sl


def rules_for(salon: Salon) -> sl.SlotRules:
    return sl.SlotRules(
        step_min=salon.slot_step_min,
        min_lead_time_min=salon.min_lead_time_min,
        horizon_days=salon.booking_horizon_days,
        tz=ZoneInfo(salon.timezone),
    )


@dataclass
class StaffOffer:
    """Мастер, оказывающий услугу, с учётом переопределений."""

    staff: Staff
    link: StaffService

    def params(self, service: Service) -> sl.ServiceParams:
        return sl.ServiceParams(
            duration_min=self.link.duration_override_min or service.duration_min,
            buffer_min=service.buffer_after_min,
        )

    def price(self, service: Service) -> int:
        return self.link.price_override if self.link.price_override is not None else service.price


async def get_active_service(session: AsyncSession, salon: Salon, service_id: int) -> Service:
    service = await session.get(Service, service_id)
    if service is None or service.salon_id != salon.id or not service.is_active:
        raise NotFound("Услуга не найдена")
    return service


async def offers_for_service(
    session: AsyncSession,
    salon: Salon,
    service: Service,
    staff_id: int | None = None,
    *,
    bookable_only: bool = True,
) -> list[StaffOffer]:
    stmt = (
        select(Staff, StaffService)
        .join(StaffService, StaffService.staff_id == Staff.id)
        .where(
            Staff.salon_id == salon.id,
            Staff.is_active.is_(True),
            StaffService.service_id == service.id,
        )
        .order_by(Staff.sort_order, Staff.id)
    )
    if bookable_only:
        stmt = stmt.where(Staff.is_bookable.is_(True))
    if staff_id is not None:
        stmt = stmt.where(Staff.id == staff_id)
    rows = (await session.execute(stmt)).all()
    offers = [StaffOffer(staff=r[0], link=r[1]) for r in rows]
    if staff_id is not None and not offers:
        raise AppError("staff_unavailable", "Мастер не оказывает эту услугу")
    return offers


def _day_bounds(day_from: date, day_to: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day_from, time(0), tzinfo=tz)
    end = datetime.combine(day_to + timedelta(days=1), time(0), tzinfo=tz)
    return start, end


async def load_schedules(
    session: AsyncSession,
    salon: Salon,
    staff: Sequence[Staff],
    day_from: date,
    day_to: date,
    *,
    exclude_appointment_id: int | None = None,
) -> dict[int, sl.StaffSchedule]:
    tz = ZoneInfo(salon.timezone)
    ids = [s.id for s in staff]
    result = {
        s.id: sl.StaffSchedule(
            staff_id=s.id,
            weekly=[],
            breaks=[],
            overrides=[],
            busy=[],
            sort_order=s.sort_order,
            appointments_per_day={},
        )
        for s in staff
    }
    if not ids:
        return result
    range_start, range_end = _day_bounds(day_from, day_to, tz)

    for w in (
        await session.execute(select(WorkSchedule).where(WorkSchedule.staff_id.in_(ids)))
    ).scalars():
        result[w.staff_id].weekly.append(sl.WeeklyInterval(w.weekday, w.start_time, w.end_time))
    for b in (
        await session.execute(select(ScheduleBreak).where(ScheduleBreak.staff_id.in_(ids)))
    ).scalars():
        result[b.staff_id].breaks.append(sl.WeeklyInterval(b.weekday, b.start_time, b.end_time))
    for o in (
        await session.execute(
            select(ScheduleOverride).where(
                ScheduleOverride.staff_id.in_(ids),
                ScheduleOverride.date >= day_from,
                ScheduleOverride.date <= day_to,
            )
        )
    ).scalars():
        result[o.staff_id].overrides.append(
            sl.OverrideInterval(o.date, o.is_day_off, o.start_time, o.end_time)
        )
    for t in (
        await session.execute(
            select(TimeOff).where(
                TimeOff.staff_id.in_(ids),
                TimeOff.starts_at < range_end,
                TimeOff.ends_at > range_start,
            )
        )
    ).scalars():
        result[t.staff_id].busy.append(sl.Busy(t.starts_at, t.ends_at))

    appt_stmt = select(
        Appointment.staff_id, Appointment.starts_at, Appointment.blocked_until
    ).where(
        Appointment.staff_id.in_(ids),
        Appointment.status.in_(ACTIVE_STATUSES),
        Appointment.starts_at < range_end,
        Appointment.blocked_until > range_start,
    )
    if exclude_appointment_id is not None:
        appt_stmt = appt_stmt.where(Appointment.id != exclude_appointment_id)
    for staff_id, starts_at, blocked_until in (await session.execute(appt_stmt)).all():
        sched = result[staff_id]
        sched.busy.append(sl.Busy(starts_at, blocked_until))
        local_day = starts_at.astimezone(tz).date()
        sched.appointments_per_day[local_day] = sched.appointments_per_day.get(local_day, 0) + 1
    return result


async def get_slots(
    session: AsyncSession,
    salon: Salon,
    service: Service,
    staff_id: int | None,
    day: date,
    now: datetime,
    *,
    exclude_appointment_id: int | None = None,
) -> list[sl.Slot]:
    offers = await offers_for_service(session, salon, service, staff_id)
    schedules = await load_schedules(
        session,
        salon,
        [o.staff for o in offers],
        day,
        day,
        exclude_appointment_id=exclude_appointment_id,
    )
    params = {o.staff.id: o.params(service) for o in offers}
    return sl.slots_for_day(list(schedules.values()), params, day, rules_for(salon), now)


async def get_days(
    session: AsyncSession,
    salon: Salon,
    service: Service,
    staff_id: int | None,
    day_from: date,
    day_to: date,
    now: datetime,
    *,
    exclude_appointment_id: int | None = None,
) -> dict[date, bool]:
    if day_to < day_from:
        raise AppError("bad_range", "Неверный диапазон дат")
    if (day_to - day_from).days > 62:
        raise AppError("bad_range", "Слишком большой диапазон дат")
    offers = await offers_for_service(session, salon, service, staff_id)
    schedules = await load_schedules(
        session,
        salon,
        [o.staff for o in offers],
        day_from,
        day_to,
        exclude_appointment_id=exclude_appointment_id,
    )
    params = {o.staff.id: o.params(service) for o in offers}
    days = [day_from + timedelta(days=i) for i in range((day_to - day_from).days + 1)]
    return sl.days_with_slots(list(schedules.values()), params, days, rules_for(salon), now)


async def nearest_slots(
    session: AsyncSession,
    salon: Salon,
    offers_by_staff: dict[int, tuple[Staff, sl.ServiceParams]],
    now: datetime,
    horizon_days: int,
) -> dict[int, datetime | None]:
    """Ближайший свободный слот для каждого мастера."""
    tz = ZoneInfo(salon.timezone)
    today = now.astimezone(tz).date()
    rules = rules_for(salon)
    days = min(horizon_days, rules.horizon_days)
    schedules = await load_schedules(
        session,
        salon,
        [s for s, _ in offers_by_staff.values()],
        today,
        today + timedelta(days=days),
    )
    return {
        staff_id: sl.nearest_slot(
            schedules[staff_id], p.duration_min, p.buffer_min, rules, now, days
        )
        for staff_id, (_, p) in offers_by_staff.items()
    }
