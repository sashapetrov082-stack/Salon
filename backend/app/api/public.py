"""Витрина салона, доступность, создание записи."""

from datetime import date, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.common import client_appointment_out, load_client_appointment
from app.api.deps import CurrentUser, NowDep, SessionDep
from app.config import settings
from app.errors import NotFound
from app.models import Client, Salon, Service, ServiceCategory, Staff, StaffService
from app.schemas.public import (
    AppointmentCreate,
    CategoryWithServices,
    ClientAppointmentOut,
    ClientProfile,
    DayAvailability,
    PhotoOut,
    SalonPublicOut,
    ServiceOut,
    SlotOut,
    StaffPublicOut,
)
from app.services import availability, booking
from app.services import slots as sl

router = APIRouter(prefix="/salons", tags=["public"])


async def get_salon_by_slug(session: AsyncSession, slug: str) -> Salon:
    salon = (
        await session.execute(
            select(Salon).where(Salon.slug == slug).options(selectinload(Salon.photos))
        )
    ).scalar_one_or_none()
    if salon is None:
        raise NotFound("Салон не найден")
    return salon


async def _appointment_scope(
    session: AsyncSession, user: CurrentUser, salon: Salon, appointment_id: int | None
) -> int | None:
    """Для экрана переноса: собственная запись не должна блокировать время."""
    if appointment_id is None:
        return None
    appt = await booking.get_client_appointment(session, user, appointment_id)
    if appt.salon_id != salon.id:
        raise NotFound("Запись не найдена")
    return appt.id


@router.get("/{slug}", response_model=SalonPublicOut)
async def get_salon(slug: str, session: SessionDep, user: CurrentUser) -> SalonPublicOut:
    salon = await get_salon_by_slug(session, slug)
    out = SalonPublicOut.model_validate(salon)
    out.photos = [PhotoOut.model_validate(p) for p in salon.photos]
    client = (
        await session.execute(
            select(Client).where(Client.salon_id == salon.id, Client.user_id == user.id)
        )
    ).scalar_one_or_none()
    if client is not None:
        out.client = ClientProfile(name=client.name, phone=client.phone)
    return out


@router.get("/{slug}/services", response_model=list[CategoryWithServices])
async def get_services(
    slug: str, session: SessionDep, _: CurrentUser
) -> list[CategoryWithServices]:
    salon = await get_salon_by_slug(session, slug)
    cats = (
        await session.execute(
            select(ServiceCategory)
            .where(ServiceCategory.salon_id == salon.id)
            .order_by(ServiceCategory.sort_order, ServiceCategory.id)
        )
    ).scalars()
    # показываем только услуги, у которых есть хотя бы один мастер для записи
    bookable = (
        select(StaffService.service_id)
        .join(Staff, Staff.id == StaffService.staff_id)
        .where(Staff.is_active.is_(True), Staff.is_bookable.is_(True))
    )
    services = (
        await session.execute(
            select(Service)
            .where(
                Service.salon_id == salon.id,
                Service.is_active.is_(True),
                Service.id.in_(bookable),
            )
            .order_by(Service.sort_order, Service.id)
        )
    ).scalars()
    by_cat: dict[int, list[ServiceOut]] = {}
    for s in services:
        by_cat.setdefault(s.category_id, []).append(ServiceOut.model_validate(s))
    return [
        CategoryWithServices(id=c.id, name=c.name, services=by_cat[c.id])
        for c in cats
        if c.id in by_cat
    ]


@router.get("/{slug}/staff", response_model=list[StaffPublicOut])
async def get_staff(
    slug: str,
    session: SessionDep,
    _: CurrentUser,
    now: NowDep,
    service_id: int | None = None,
) -> list[StaffPublicOut]:
    salon = await get_salon_by_slug(session, slug)
    staff_rows = (
        (
            await session.execute(
                select(Staff)
                .where(
                    Staff.salon_id == salon.id,
                    Staff.is_active.is_(True),
                    Staff.is_bookable.is_(True),
                )
                .order_by(Staff.sort_order, Staff.id)
            )
        )
        .scalars()
        .all()
    )
    links = (
        await session.execute(
            select(StaffService, Service)
            .join(Service, Service.id == StaffService.service_id)
            .where(
                StaffService.staff_id.in_([s.id for s in staff_rows]),
                Service.is_active.is_(True),
            )
        )
    ).all()
    by_staff: dict[int, list[tuple[StaffService, Service]]] = {}
    for link, service in links:
        by_staff.setdefault(link.staff_id, []).append((link, service))

    result: list[StaffPublicOut] = []
    params: dict[int, tuple[Staff, sl.ServiceParams]] = {}
    for staff in staff_rows:
        offers = by_staff.get(staff.id, [])
        if service_id is not None:
            offers = [o for o in offers if o[1].id == service_id]
        if not offers:
            continue
        out = StaffPublicOut.model_validate(staff)
        if service_id is not None:
            link, service = offers[0]
            offer = availability.StaffOffer(staff=staff, link=link)
            out.price = offer.price(service)
            out.price_is_from = service.price_is_from
            out.duration_min = offer.params(service).duration_min
            params[staff.id] = (staff, offer.params(service))
        else:
            # для ближайшего слота берём самую короткую из услуг мастера
            shortest = min(
                (availability.StaffOffer(staff=staff, link=lk).params(sv) for lk, sv in offers),
                key=lambda p: (p.duration_min, p.buffer_min),
            )
            params[staff.id] = (staff, shortest)
        result.append(out)

    nearest = await availability.nearest_slots(
        session, salon, params, now, settings.nearest_slot_horizon_days
    )
    for out in result:
        out.nearest_slot = nearest.get(out.id)
    return result


@router.get("/{slug}/availability/days", response_model=list[DayAvailability])
async def get_available_days(
    slug: str,
    service_id: int,
    session: SessionDep,
    user: CurrentUser,
    now: NowDep,
    staff_id: int | None = None,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    appointment_id: int | None = None,
) -> list[DayAvailability]:
    salon = await get_salon_by_slug(session, slug)
    service = await availability.get_active_service(session, salon, service_id)
    today = now.astimezone(ZoneInfo(salon.timezone)).date()
    day_from = from_ or today
    day_to = to or today + timedelta(days=salon.booking_horizon_days - 1)
    exclude = await _appointment_scope(session, user, salon, appointment_id)
    days = await availability.get_days(
        session, salon, service, staff_id, day_from, day_to, now, exclude_appointment_id=exclude
    )
    return [DayAvailability(date=d, has_slots=v) for d, v in sorted(days.items())]


@router.get("/{slug}/availability/slots", response_model=list[SlotOut])
async def get_available_slots(
    slug: str,
    service_id: int,
    date: date,
    session: SessionDep,
    user: CurrentUser,
    now: NowDep,
    staff_id: int | None = None,
    appointment_id: int | None = None,
) -> list[SlotOut]:
    salon = await get_salon_by_slug(session, slug)
    service = await availability.get_active_service(session, salon, service_id)
    exclude = await _appointment_scope(session, user, salon, appointment_id)
    slots = await availability.get_slots(
        session, salon, service, staff_id, date, now, exclude_appointment_id=exclude
    )
    return [SlotOut(starts_at=s.starts_at, staff_id=s.staff_id) for s in slots]


@router.post("/{slug}/appointments", response_model=ClientAppointmentOut, status_code=201)
async def create_appointment(
    slug: str, body: AppointmentCreate, session: SessionDep, user: CurrentUser, now: NowDep
) -> ClientAppointmentOut:
    salon = await get_salon_by_slug(session, slug)
    appt = await booking.create_client_appointment(
        session,
        salon,
        user,
        booking.ClientBookingRequest(
            service_id=body.service_id,
            staff_id=body.staff_id,
            starts_at=body.starts_at,
            name=body.name,
            phone=body.phone,
            comment=body.comment,
        ),
        now,
    )
    full = await load_client_appointment(session, appt.id)
    return client_appointment_out(full, now)
