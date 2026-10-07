"""Создание, перенос, отмена и смена статуса записей."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import AppError, Forbidden, NotFound, SlotTaken
from app.models import (
    ACTIVE_STATUSES,
    Appointment,
    AppointmentSource,
    AppointmentStatus,
    Client,
    Salon,
    Service,
    User,
    UserContact,
)
from app.services import notifications
from app.services import slots as sl
from app.services.availability import (
    StaffOffer,
    get_active_service,
    load_schedules,
    offers_for_service,
    rules_for,
)
from app.services.formatting import normalize_phone

EXCLUSION_VIOLATION = "23P01"

STAFF_STATUSES = (
    AppointmentStatus.completed,
    AppointmentStatus.no_show,
    AppointmentStatus.cancelled_by_salon,
)


def _is_exclusion_violation(e: IntegrityError) -> bool:
    orig = e.orig
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if code is None and orig is not None:
        code = getattr(orig.__cause__, "sqlstate", None)
    return code == EXCLUSION_VIOLATION


async def _flush_or_slot_taken(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        if _is_exclusion_violation(e):
            raise SlotTaken() from e
        raise


def _ensure_salon_active(salon: Salon) -> None:
    if not salon.is_active:
        raise AppError("salon_inactive", "Салон временно не принимает записи")


async def _choose_offer(
    session: AsyncSession,
    salon: Salon,
    service: Service,
    staff_id: int | None,
    starts_at: datetime,
    now: datetime,
    *,
    exclude_appointment_id: int | None = None,
) -> StaffOffer:
    """Повторная проверка слота; для «любого мастера» — выбор мастера по правилам."""
    offers = await offers_for_service(session, salon, service, staff_id)
    if not offers:
        raise AppError("staff_unavailable", "Нет мастеров для этой услуги")
    rules = rules_for(salon)
    day = starts_at.astimezone(rules.tz).date()
    schedules = await load_schedules(
        session,
        salon,
        [o.staff for o in offers],
        day,
        day,
        exclude_appointment_id=exclude_appointment_id,
    )
    available = [
        o
        for o in offers
        if sl.is_slot_available(
            schedules[o.staff.id],
            starts_at,
            o.params(service).duration_min,
            o.params(service).buffer_min,
            rules,
            now,
        )
    ]
    if not available:
        raise SlotTaken()
    chosen = sl.pick_staff([schedules[o.staff.id] for o in available], day)
    return next(o for o in available if o.staff.id == chosen.staff_id)


def _apply_time(
    appt: Appointment, offer: StaffOffer, service: Service, starts_at: datetime
) -> None:
    params = offer.params(service)
    appt.staff_id = offer.staff.id
    appt.starts_at = starts_at
    appt.ends_at = starts_at + timedelta(minutes=params.duration_min)
    appt.blocked_until = appt.ends_at + timedelta(minutes=params.buffer_min)


async def _get_or_create_client_for_user(
    session: AsyncSession, salon: Salon, user: User, name: str, phone: str
) -> Client:
    await session.execute(
        insert(Client)
        .values(salon_id=salon.id, user_id=user.id, name=name, phone=phone)
        .on_conflict_do_nothing(
            index_elements=[Client.salon_id, Client.user_id],
            index_where=Client.user_id.is_not(None),
        )
    )
    client = (
        await session.execute(
            select(Client).where(Client.salon_id == salon.id, Client.user_id == user.id)
        )
    ).scalar_one()
    client.name = name
    client.phone = phone
    return client


async def resolve_client_phone(
    session: AsyncSession, salon: Salon, user: User, phone: str | None
) -> str | None:
    if phone:
        normalized = normalize_phone(phone)
        if normalized is None:
            raise AppError("invalid_phone", "Проверьте номер телефона")
        return normalized
    contact = await session.get(UserContact, user.id)
    if contact is not None:
        return contact.phone
    existing = (
        await session.execute(
            select(Client.phone).where(Client.salon_id == salon.id, Client.user_id == user.id)
        )
    ).scalar_one_or_none()
    return existing


@dataclass
class ClientBookingRequest:
    service_id: int
    staff_id: int | None
    starts_at: datetime
    name: str
    phone: str | None = None
    comment: str | None = None


async def create_client_appointment(
    session: AsyncSession, salon: Salon, user: User, req: ClientBookingRequest, now: datetime
) -> Appointment:
    _ensure_salon_active(salon)
    service = await get_active_service(session, salon, req.service_id)
    name = req.name.strip()
    if not name:
        raise AppError("name_required", "Укажите имя")
    phone = await resolve_client_phone(session, salon, user, req.phone)
    if not phone:
        raise AppError("phone_required", "Укажите номер телефона")

    offer = await _choose_offer(session, salon, service, req.staff_id, req.starts_at, now)
    client = await _get_or_create_client_for_user(session, salon, user, name, phone)

    active_count = (
        await session.execute(
            select(func.count())
            .select_from(Appointment)
            .where(
                Appointment.client_id == client.id,
                Appointment.status.in_(ACTIVE_STATUSES),
                Appointment.starts_at > now,
            )
        )
    ).scalar_one()
    limit = settings.max_active_appointments_per_client
    if active_count >= limit:
        await session.rollback()
        raise AppError(
            "too_many_appointments",
            f"У вас уже {limit} активные записи в этом салоне. "
            "Отмените одну из них или позвоните в салон.",
        )

    appt = Appointment(
        salon_id=salon.id,
        client_id=client.id,
        service_id=service.id,
        status=AppointmentStatus.booked,
        source=AppointmentSource.client_app,
        price=offer.price(service),
        price_is_from=service.price_is_from,
        comment=(req.comment or "").strip() or None,
        created_by_user_id=user.id,
    )
    _apply_time(appt, offer, service, req.starts_at)
    session.add(appt)
    await _flush_or_slot_taken(session)
    await notifications.schedule_for_booking(session, appt, now, actor_user_id=None)
    await session.commit()
    return appt


@dataclass
class ManualBookingRequest:
    staff_id: int
    service_id: int
    starts_at: datetime
    client_id: int | None = None
    client_name: str | None = None
    client_phone: str | None = None
    comment: str | None = None


async def create_manual_appointment(
    session: AsyncSession, salon: Salon, actor: User, req: ManualBookingRequest, now: datetime
) -> Appointment:
    """Ручная запись мастером/админом. Сетка и окно записи не проверяются —
    только активность мастера/услуги и пересечения (ограничение в БД)."""
    service = await session.get(Service, req.service_id)
    if service is None or service.salon_id != salon.id:
        raise NotFound("Услуга не найдена")
    offers = await offers_for_service(session, salon, service, req.staff_id, bookable_only=False)
    offer = offers[0]

    if req.client_id is not None:
        client = await session.get(Client, req.client_id)
        if client is None or client.salon_id != salon.id:
            raise NotFound("Клиент не найден")
    else:
        name = (req.client_name or "").strip()
        phone = normalize_phone(req.client_phone or "")
        if not name or not phone:
            raise AppError("client_required", "Укажите имя и телефон клиента")
        client = Client(salon_id=salon.id, user_id=None, name=name, phone=phone)
        session.add(client)
        await session.flush()

    appt = Appointment(
        salon_id=salon.id,
        client_id=client.id,
        service_id=service.id,
        status=AppointmentStatus.booked,
        source=AppointmentSource.manual,
        price=offer.price(service),
        price_is_from=service.price_is_from,
        comment=(req.comment or "").strip() or None,
        created_by_user_id=actor.id,
    )
    _apply_time(appt, offer, service, req.starts_at)
    session.add(appt)
    await _flush_or_slot_taken(session)
    await notifications.schedule_for_booking(session, appt, now, actor_user_id=actor.id)
    await session.commit()
    return appt


async def get_client_appointment(
    session: AsyncSession, user: User, appointment_id: int
) -> Appointment:
    appt = await session.get(Appointment, appointment_id)
    if appt is None:
        raise NotFound("Запись не найдена")
    client = await session.get(Client, appt.client_id)
    if client is None or client.user_id != user.id:
        raise NotFound("Запись не найдена")
    return appt


def can_client_change(appt: Appointment, salon: Salon, now: datetime) -> bool:
    return appt.is_active and appt.starts_at - now >= timedelta(hours=salon.cancel_deadline_hours)


def _ensure_client_can_change(appt: Appointment, salon: Salon, now: datetime) -> None:
    if not appt.is_active:
        raise AppError("not_active", "Запись уже неактивна")
    if not can_client_change(appt, salon, now):
        raise AppError(
            "deadline_passed",
            f"Отменить или перенести запись можно не позже чем за "
            f"{salon.cancel_deadline_hours} ч. Позвоните в салон.",
        )


async def cancel_by_client(
    session: AsyncSession, user: User, appointment_id: int, now: datetime
) -> Appointment:
    appt = await get_client_appointment(session, user, appointment_id)
    salon = await session.get(Salon, appt.salon_id)
    assert salon is not None
    _ensure_client_can_change(appt, salon, now)
    appt.status = AppointmentStatus.cancelled_by_client
    await notifications.schedule_for_client_cancel(session, appt, now)
    await session.commit()
    return appt


async def reschedule(
    session: AsyncSession,
    appt: Appointment,
    starts_at: datetime,
    staff_id: int | None,
    now: datetime,
    *,
    actor: User,
    by_client: bool,
) -> Appointment:
    salon = await session.get(Salon, appt.salon_id)
    service = await session.get(Service, appt.service_id)
    assert salon is not None and service is not None
    if by_client:
        _ensure_salon_active(salon)
        _ensure_client_can_change(appt, salon, now)
        if not service.is_active:
            raise AppError("service_inactive", "Услуга больше недоступна")
        offer = await _choose_offer(
            session,
            salon,
            service,
            staff_id if staff_id is not None else appt.staff_id,
            starts_at,
            now,
            exclude_appointment_id=appt.id,
        )
    else:
        if not appt.is_active:
            raise AppError("not_active", "Запись уже неактивна")
        target_staff = staff_id if staff_id is not None else appt.staff_id
        offer = (
            await offers_for_service(session, salon, service, target_staff, bookable_only=False)
        )[0]
    _apply_time(appt, offer, service, starts_at)
    await _flush_or_slot_taken(session)
    await notifications.schedule_for_booking(
        session, appt, now, rescheduled=True, actor_user_id=None if by_client else actor.id
    )
    await session.commit()
    return appt


async def confirm_by_client(
    session: AsyncSession, user: User, appointment_id: int, now: datetime
) -> Appointment:
    appt = await get_client_appointment(session, user, appointment_id)
    if appt.status == AppointmentStatus.confirmed:
        return appt
    if appt.status != AppointmentStatus.booked or appt.starts_at <= now:
        raise AppError("not_active", "Запись уже неактивна")
    appt.status = AppointmentStatus.confirmed
    await session.commit()
    return appt


def _counter_delta(status: AppointmentStatus) -> tuple[int, int]:
    if status == AppointmentStatus.completed:
        return 1, 0
    if status == AppointmentStatus.no_show:
        return 0, 1
    return 0, 0


async def set_status_by_staff(
    session: AsyncSession, appt: Appointment, status: AppointmentStatus, now: datetime
) -> Appointment:
    if status not in STAFF_STATUSES:
        raise AppError("bad_status", "Недопустимый статус")
    old = appt.status
    if old == status:
        return appt
    correction = {old, status} == {AppointmentStatus.completed, AppointmentStatus.no_show}
    if not appt.is_active and not correction:
        raise AppError("not_active", "Запись уже неактивна")

    client = await session.get(Client, appt.client_id, with_for_update=True)
    assert client is not None
    old_v, old_n = _counter_delta(old)
    new_v, new_n = _counter_delta(status)
    client.visits_count = max(0, client.visits_count - old_v + new_v)
    client.no_show_count = max(0, client.no_show_count - old_n + new_n)

    appt.status = status
    if status == AppointmentStatus.cancelled_by_salon:
        await notifications.schedule_for_salon_cancel(session, appt, now)
    else:
        await notifications.cancel_pending(session, appt.id)
    await session.commit()
    return appt


async def ensure_user_owns(session: AsyncSession, user: User, appt: Appointment) -> None:
    client = await session.get(Client, appt.client_id)
    if client is None or client.user_id != user.id:
        raise Forbidden()
