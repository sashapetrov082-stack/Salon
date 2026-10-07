"""Постановка уведомлений в таблицу notification (отправляет worker.py)."""

from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Appointment,
    Client,
    Notification,
    NotificationKind,
    NotificationStatus,
    Staff,
)

REMINDERS = (
    (NotificationKind.reminder_24h, timedelta(hours=24)),
    (NotificationKind.reminder_2h, timedelta(hours=2)),
)


async def cancel_pending(session: AsyncSession, appointment_id: int) -> None:
    await session.execute(
        update(Notification)
        .where(
            Notification.appointment_id == appointment_id,
            Notification.status == NotificationStatus.pending,
        )
        .values(status=NotificationStatus.cancelled)
    )


async def _recipients(session: AsyncSession, appt: Appointment) -> tuple[int | None, int | None]:
    client = await session.get(Client, appt.client_id)
    staff = await session.get(Staff, appt.staff_id)
    return (client.user_id if client else None, staff.user_id if staff else None)


def _add(
    session: AsyncSession, appt: Appointment, user_id: int, kind: NotificationKind, at: datetime
) -> None:
    session.add(
        Notification(
            appointment_id=appt.id,
            recipient_user_id=user_id,
            kind=kind,
            send_at=at,
            status=NotificationStatus.pending,
            attempts=0,
        )
    )


async def schedule_for_booking(
    session: AsyncSession,
    appt: Appointment,
    now: datetime,
    *,
    rescheduled: bool = False,
    actor_user_id: int | None = None,
) -> None:
    """Создание или перенос записи: старые pending → cancelled, затем новые уведомления.

    actor_user_id — кто совершил действие; себе уведомление не отправляем.
    """
    await cancel_pending(session, appt.id)
    client_user_id, staff_user_id = await _recipients(session, appt)
    if client_user_id is not None:
        if client_user_id != actor_user_id:
            _add(session, appt, client_user_id, NotificationKind.client_booked, now)
        for kind, delta in REMINDERS:
            send_at = appt.starts_at - delta
            if send_at > now:
                _add(session, appt, client_user_id, kind, send_at)
    if staff_user_id is not None and staff_user_id != actor_user_id:
        kind = NotificationKind.staff_rescheduled if rescheduled else NotificationKind.staff_new
        _add(session, appt, staff_user_id, kind, now)


async def schedule_for_client_cancel(
    session: AsyncSession, appt: Appointment, now: datetime
) -> None:
    await cancel_pending(session, appt.id)
    _, staff_user_id = await _recipients(session, appt)
    if staff_user_id is not None:
        _add(session, appt, staff_user_id, NotificationKind.staff_cancelled, now)


async def schedule_for_salon_cancel(
    session: AsyncSession, appt: Appointment, now: datetime
) -> None:
    await cancel_pending(session, appt.id)
    client_user_id, _ = await _recipients(session, appt)
    if client_user_id is not None:
        _add(session, appt, client_user_id, NotificationKind.client_cancelled_by_salon, now)
