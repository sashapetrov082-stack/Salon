"""Календарь записей, ручные записи, смена статуса и перенос."""

from datetime import date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import NowDep, SessionDep, StaffContext, StaffDep
from app.api.manage.helpers import get_salon_staff
from app.errors import AppError, NotFound
from app.models import Appointment, Staff, TimeOff
from app.schemas.manage import (
    AppointmentPatch,
    CalendarOut,
    ManageAppointmentOut,
    ManualAppointmentIn,
    StaffCalendarOut,
    TimeOffOut,
)
from app.services import booking

router = APIRouter()

OPTIONS = (selectinload(Appointment.service), selectinload(Appointment.client))


async def _load(session: SessionDep, ctx: StaffContext, appointment_id: int) -> Appointment:
    appt = await session.get(Appointment, appointment_id, options=OPTIONS, populate_existing=True)
    if appt is None or appt.salon_id != ctx.salon.id:
        raise NotFound("Запись не найдена")
    ctx.ensure_can_manage_staff(appt.staff_id)
    return appt


@router.get("/calendar", response_model=CalendarOut)
async def calendar(
    session: SessionDep,
    ctx: StaffDep,
    now: NowDep,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    staff_id: int | None = None,
) -> CalendarOut:
    tz = ZoneInfo(ctx.salon.timezone)
    day_from = from_ or now.astimezone(tz).date()
    day_to = to or day_from
    if day_to < day_from or (day_to - day_from).days > 62:
        raise AppError("bad_range", "Неверный диапазон дат")
    start = datetime.combine(day_from, time(0), tzinfo=tz)
    end = datetime.combine(day_to + timedelta(days=1), time(0), tzinfo=tz)

    if not ctx.is_admin:
        staff_id = ctx.staff.id
    staff_stmt = (
        select(Staff)
        .where(Staff.salon_id == ctx.salon.id, Staff.is_active.is_(True))
        .order_by(Staff.sort_order, Staff.id)
    )
    if staff_id is not None:
        staff_stmt = staff_stmt.where(Staff.id == staff_id)
    staff = (await session.execute(staff_stmt)).scalars().all()
    ids = [s.id for s in staff]

    appts = (
        (
            await session.execute(
                select(Appointment)
                .where(
                    Appointment.salon_id == ctx.salon.id,
                    Appointment.staff_id.in_(ids),
                    Appointment.starts_at < end,
                    Appointment.ends_at > start,
                )
                .options(*OPTIONS)
                .order_by(Appointment.starts_at)
            )
        )
        .scalars()
        .all()
    )
    time_off = (
        (
            await session.execute(
                select(TimeOff)
                .where(TimeOff.staff_id.in_(ids), TimeOff.starts_at < end, TimeOff.ends_at > start)
                .order_by(TimeOff.starts_at)
            )
        )
        .scalars()
        .all()
    )
    return CalendarOut(
        appointments=[ManageAppointmentOut.model_validate(a) for a in appts],
        time_off=[TimeOffOut.model_validate(t) for t in time_off],
        staff=[StaffCalendarOut.model_validate(s) for s in staff],
    )


@router.post("/appointments", response_model=ManageAppointmentOut, status_code=201)
async def create_manual(
    body: ManualAppointmentIn, session: SessionDep, ctx: StaffDep, now: NowDep
) -> ManageAppointmentOut:
    await get_salon_staff(session, ctx, body.staff_id)
    appt = await booking.create_manual_appointment(
        session,
        ctx.salon,
        ctx.user,
        booking.ManualBookingRequest(
            staff_id=body.staff_id,
            service_id=body.service_id,
            starts_at=body.starts_at,
            client_id=body.client_id,
            client_name=body.client.name if body.client else None,
            client_phone=body.client.phone if body.client else None,
            comment=body.comment,
        ),
        now,
    )
    return ManageAppointmentOut.model_validate(await _load(session, ctx, appt.id))


@router.get("/appointments/{appointment_id}", response_model=ManageAppointmentOut)
async def get_appointment(
    appointment_id: int, session: SessionDep, ctx: StaffDep
) -> ManageAppointmentOut:
    return ManageAppointmentOut.model_validate(await _load(session, ctx, appointment_id))


@router.patch("/appointments/{appointment_id}", response_model=ManageAppointmentOut)
async def patch_appointment(
    appointment_id: int, body: AppointmentPatch, session: SessionDep, ctx: StaffDep, now: NowDep
) -> ManageAppointmentOut:
    appt = await _load(session, ctx, appointment_id)
    if body.status is not None and (body.starts_at is not None or body.staff_id is not None):
        raise AppError("bad_request", "Нельзя одновременно менять статус и время")
    if body.starts_at is not None or body.staff_id is not None:
        if body.staff_id is not None:
            await get_salon_staff(session, ctx, body.staff_id)
        await booking.reschedule(
            session,
            appt,
            body.starts_at or appt.starts_at,
            body.staff_id,
            now,
            actor=ctx.user,
            by_client=False,
        )
    elif body.status is not None:
        await booking.set_status_by_staff(session, appt, body.status, now)
    return ManageAppointmentOut.model_validate(await _load(session, ctx, appointment_id))
