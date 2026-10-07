"""Профиль клиента и «мои записи»."""

from typing import Literal

from fastapi import APIRouter
from sqlalchemy import select

from app.api.common import APPOINTMENT_OPTIONS, client_appointment_out, load_client_appointment
from app.api.deps import CurrentUser, NowDep, SessionDep
from app.models import ACTIVE_STATUSES, Appointment, Client, Salon, Staff, UserContact
from app.schemas.me import ContactStatus, MeOut, RescheduleIn, StaffSalon, VisitedSalon
from app.schemas.public import ClientAppointmentOut
from app.services import booking

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeOut)
async def get_me(session: SessionDep, user: CurrentUser) -> MeOut:
    staff_rows = (
        await session.execute(
            select(Staff, Salon)
            .join(Salon, Salon.id == Staff.salon_id)
            .where(Staff.user_id == user.id, Staff.is_active.is_(True))
            .order_by(Salon.name)
        )
    ).all()
    visited = (
        (
            await session.execute(
                select(Salon)
                .join(Client, Client.salon_id == Salon.id)
                .where(Client.user_id == user.id)
                .order_by(Salon.name)
            )
        )
        .scalars()
        .all()
    )
    return MeOut(
        id=user.id,
        telegram_id=user.telegram_id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        is_staff=bool(staff_rows),
        staff_salons=[
            StaffSalon(
                salon_id=salon.id,
                salon_name=salon.name,
                salon_slug=salon.slug,
                staff_id=staff.id,
                role=staff.role.value,
            )
            for staff, salon in staff_rows
        ],
        visited_salons=[VisitedSalon.model_validate(s) for s in visited],
    )


@router.get("/contact-status", response_model=ContactStatus)
async def contact_status(session: SessionDep, user: CurrentUser) -> ContactStatus:
    contact = await session.get(UserContact, user.id, populate_existing=True)
    if contact is None:
        return ContactStatus(received=False)
    return ContactStatus(received=True, phone=contact.phone)


@router.get("/appointments", response_model=list[ClientAppointmentOut])
async def my_appointments(
    session: SessionDep,
    user: CurrentUser,
    now: NowDep,
    scope: Literal["upcoming", "past"] = "upcoming",
) -> list[ClientAppointmentOut]:
    stmt = (
        select(Appointment)
        .join(Client, Client.id == Appointment.client_id)
        .where(Client.user_id == user.id)
        .options(*APPOINTMENT_OPTIONS)
    )
    if scope == "upcoming":
        stmt = stmt.where(
            Appointment.status.in_(ACTIVE_STATUSES), Appointment.ends_at > now
        ).order_by(Appointment.starts_at)
    else:
        stmt = (
            stmt.where((Appointment.status.not_in(ACTIVE_STATUSES)) | (Appointment.ends_at <= now))
            .order_by(Appointment.starts_at.desc())
            .limit(100)
        )
    rows = (await session.execute(stmt)).scalars().all()
    return [client_appointment_out(a, now) for a in rows]


@router.get("/appointments/{appointment_id}", response_model=ClientAppointmentOut)
async def my_appointment(
    appointment_id: int, session: SessionDep, user: CurrentUser, now: NowDep
) -> ClientAppointmentOut:
    appt = await booking.get_client_appointment(session, user, appointment_id)
    return client_appointment_out(await load_client_appointment(session, appt.id), now)


@router.post("/appointments/{appointment_id}/cancel", response_model=ClientAppointmentOut)
async def cancel(
    appointment_id: int, session: SessionDep, user: CurrentUser, now: NowDep
) -> ClientAppointmentOut:
    appt = await booking.cancel_by_client(session, user, appointment_id, now)
    return client_appointment_out(await load_client_appointment(session, appt.id), now)


@router.post("/appointments/{appointment_id}/reschedule", response_model=ClientAppointmentOut)
async def reschedule(
    appointment_id: int, body: RescheduleIn, session: SessionDep, user: CurrentUser, now: NowDep
) -> ClientAppointmentOut:
    appt = await booking.get_client_appointment(session, user, appointment_id)
    appt = await booking.reschedule(
        session, appt, body.starts_at, body.staff_id, now, actor=user, by_client=True
    )
    return client_appointment_out(await load_client_appointment(session, appt.id), now)


@router.post("/appointments/{appointment_id}/confirm", response_model=ClientAppointmentOut)
async def confirm(
    appointment_id: int, session: SessionDep, user: CurrentUser, now: NowDep
) -> ClientAppointmentOut:
    appt = await booking.confirm_by_client(session, user, appointment_id, now)
    return client_appointment_out(await load_client_appointment(session, appt.id), now)
