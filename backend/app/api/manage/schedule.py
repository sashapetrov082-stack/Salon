"""График мастера: недельный шаблон, перерывы, исключения, блокировки."""

from datetime import date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from sqlalchemy import delete, select

from app.api.deps import NowDep, SessionDep, StaffDep
from app.api.manage.helpers import get_salon_staff
from app.errors import NotFound
from app.models import ScheduleBreak, ScheduleOverride, TimeOff, WorkSchedule
from app.schemas.common import Ok
from app.schemas.manage import (
    OverrideIn,
    OverrideOut,
    ScheduleIn,
    ScheduleOut,
    TimeOffIn,
    TimeOffOut,
    WeeklyOut,
)

router = APIRouter(prefix="/staff/{staff_id}")


async def _schedule(session: SessionDep, staff_id: int) -> ScheduleOut:
    work = (
        await session.execute(
            select(WorkSchedule)
            .where(WorkSchedule.staff_id == staff_id)
            .order_by(WorkSchedule.weekday, WorkSchedule.start_time)
        )
    ).scalars()
    breaks = (
        await session.execute(
            select(ScheduleBreak)
            .where(ScheduleBreak.staff_id == staff_id)
            .order_by(ScheduleBreak.weekday, ScheduleBreak.start_time)
        )
    ).scalars()
    return ScheduleOut(
        work=[WeeklyOut.model_validate(w) for w in work],
        breaks=[WeeklyOut.model_validate(b) for b in breaks],
    )


@router.get("/schedule", response_model=ScheduleOut)
async def get_schedule(staff_id: int, session: SessionDep, ctx: StaffDep) -> ScheduleOut:
    await get_salon_staff(session, ctx, staff_id)
    return await _schedule(session, staff_id)


@router.put("/schedule", response_model=ScheduleOut)
async def put_schedule(
    staff_id: int, body: ScheduleIn, session: SessionDep, ctx: StaffDep
) -> ScheduleOut:
    await get_salon_staff(session, ctx, staff_id)
    await session.execute(delete(WorkSchedule).where(WorkSchedule.staff_id == staff_id))
    await session.execute(delete(ScheduleBreak).where(ScheduleBreak.staff_id == staff_id))
    for w in body.work:
        session.add(
            WorkSchedule(
                staff_id=staff_id, weekday=w.weekday, start_time=w.start_time, end_time=w.end_time
            )
        )
    for b in body.breaks:
        session.add(
            ScheduleBreak(
                staff_id=staff_id, weekday=b.weekday, start_time=b.start_time, end_time=b.end_time
            )
        )
    await session.commit()
    return await _schedule(session, staff_id)


@router.get("/overrides", response_model=list[OverrideOut])
async def list_overrides(
    staff_id: int,
    session: SessionDep,
    ctx: StaffDep,
    now: NowDep,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> list[OverrideOut]:
    await get_salon_staff(session, ctx, staff_id)
    day_from = from_ or now.astimezone(ZoneInfo(ctx.salon.timezone)).date()
    stmt = select(ScheduleOverride).where(
        ScheduleOverride.staff_id == staff_id, ScheduleOverride.date >= day_from
    )
    if to is not None:
        stmt = stmt.where(ScheduleOverride.date <= to)
    rows = (
        await session.execute(stmt.order_by(ScheduleOverride.date, ScheduleOverride.start_time))
    ).scalars()
    return [OverrideOut.model_validate(o) for o in rows]


@router.post("/overrides", response_model=OverrideOut, status_code=201)
async def create_override(
    staff_id: int, body: OverrideIn, session: SessionDep, ctx: StaffDep
) -> OverrideOut:
    await get_salon_staff(session, ctx, staff_id)
    if body.is_day_off:
        # выходной заменяет все интервалы этой даты
        await session.execute(
            delete(ScheduleOverride).where(
                ScheduleOverride.staff_id == staff_id, ScheduleOverride.date == body.date
            )
        )
    else:
        await session.execute(
            delete(ScheduleOverride).where(
                ScheduleOverride.staff_id == staff_id,
                ScheduleOverride.date == body.date,
                ScheduleOverride.is_day_off.is_(True),
            )
        )
    row = ScheduleOverride(staff_id=staff_id, **body.model_dump())
    session.add(row)
    await session.commit()
    return OverrideOut.model_validate(row)


@router.delete("/overrides/{override_id}", response_model=Ok)
async def delete_override(
    staff_id: int, override_id: int, session: SessionDep, ctx: StaffDep
) -> Ok:
    await get_salon_staff(session, ctx, staff_id)
    row = await session.get(ScheduleOverride, override_id)
    if row is None or row.staff_id != staff_id:
        raise NotFound()
    await session.delete(row)
    await session.commit()
    return Ok()


@router.get("/time-off", response_model=list[TimeOffOut])
async def list_time_off(
    staff_id: int,
    session: SessionDep,
    ctx: StaffDep,
    now: NowDep,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> list[TimeOffOut]:
    await get_salon_staff(session, ctx, staff_id)
    tz = ZoneInfo(ctx.salon.timezone)
    start = datetime.combine(from_ or now.astimezone(tz).date(), time(0), tzinfo=tz)
    stmt = select(TimeOff).where(TimeOff.staff_id == staff_id, TimeOff.ends_at > start)
    if to is not None:
        stmt = stmt.where(
            TimeOff.starts_at < datetime.combine(to + timedelta(days=1), time(0), tzinfo=tz)
        )
    rows = (await session.execute(stmt.order_by(TimeOff.starts_at))).scalars()
    return [TimeOffOut.model_validate(t) for t in rows]


@router.post("/time-off", response_model=TimeOffOut, status_code=201)
async def create_time_off(
    staff_id: int, body: TimeOffIn, session: SessionDep, ctx: StaffDep
) -> TimeOffOut:
    await get_salon_staff(session, ctx, staff_id)
    row = TimeOff(staff_id=staff_id, **body.model_dump())
    session.add(row)
    await session.commit()
    return TimeOffOut.model_validate(row)


@router.delete("/time-off/{time_off_id}", response_model=Ok)
async def delete_time_off(
    staff_id: int, time_off_id: int, session: SessionDep, ctx: StaffDep
) -> Ok:
    await get_salon_staff(session, ctx, staff_id)
    row = await session.get(TimeOff, time_off_id)
    if row is None or row.staff_id != staff_id:
        raise NotFound()
    await session.delete(row)
    await session.commit()
    return Ok()
