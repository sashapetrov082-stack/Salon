"""Воркер отправки уведомлений: python -m app.worker"""

import asyncio
import logging
import signal
import time
from datetime import UTC, datetime, timedelta
from typing import Protocol

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.bot import keyboards, texts
from app.models import (
    Appointment,
    AppointmentStatus,
    Notification,
    NotificationKind,
    NotificationStatus,
    User,
)

log = logging.getLogger("app.worker")

POLL_INTERVAL_SECONDS = 20
BATCH_SIZE = 50
MAX_ATTEMPTS = 5
MAX_PER_SECOND = 25

# Эти уведомления имеют смысл только пока запись активна
REQUIRES_ACTIVE = {
    NotificationKind.reminder_24h,
    NotificationKind.reminder_2h,
    NotificationKind.client_booked,
    NotificationKind.staff_new,
    NotificationKind.staff_rescheduled,
}


class RecipientBlocked(Exception):
    """Пользователь заблокировал бота."""


class Sender(Protocol):
    async def send(self, chat_id: int, kind: NotificationKind, appt: Appointment) -> None: ...


class TelegramSender:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def send(self, chat_id: int, kind: NotificationKind, appt: Appointment) -> None:
        try:
            await self.bot.send_message(
                chat_id,
                texts.notification_text(kind, appt),
                reply_markup=keyboards.for_notification(kind, appt),
                disable_web_page_preview=True,
            )
        except TelegramForbiddenError as e:
            raise RecipientBlocked(str(e)) from e
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            raise


class RateLimiter:
    def __init__(self, per_second: int) -> None:
        self.interval = 1.0 / per_second
        self._next = 0.0

    async def wait(self) -> None:
        now = time.monotonic()
        if self._next > now:
            await asyncio.sleep(self._next - now)
        self._next = max(now, self._next) + self.interval


def retry_delay(attempts: int) -> timedelta:
    return timedelta(minutes=2**attempts)


def _still_relevant(n: Notification, appt: Appointment, now: datetime) -> bool:
    if n.kind not in REQUIRES_ACTIVE:
        return True
    if appt.status not in (AppointmentStatus.booked, AppointmentStatus.confirmed):
        return False
    return not (
        n.kind in (NotificationKind.reminder_24h, NotificationKind.reminder_2h)
        and appt.starts_at <= now
    )


async def process_batch(
    session: AsyncSession,
    sender: Sender,
    now: datetime,
    limiter: RateLimiter | None = None,
    limit: int = BATCH_SIZE,
) -> int:
    """Обрабатывает одну пачку уведомлений. Возвращает число обработанных."""
    rows = (
        (
            await session.execute(
                select(Notification)
                .where(
                    Notification.status == NotificationStatus.pending, Notification.send_at <= now
                )
                .order_by(Notification.send_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for n in rows:
        appt = await session.get(
            Appointment,
            n.appointment_id,
            options=[
                selectinload(Appointment.salon),
                selectinload(Appointment.service),
                selectinload(Appointment.staff),
                selectinload(Appointment.client),
            ],
        )
        user = await session.get(User, n.recipient_user_id)
        if appt is None or user is None or not _still_relevant(n, appt, now):
            n.status = NotificationStatus.cancelled
            continue
        if user.bot_blocked:
            n.status = NotificationStatus.failed
            n.last_error = "bot blocked by user"
            continue
        if limiter is not None:
            await limiter.wait()
        try:
            await sender.send(user.telegram_id, n.kind, appt)
        except RecipientBlocked as e:
            n.status = NotificationStatus.failed
            n.last_error = str(e)[:500]
            user.bot_blocked = True
            log.info("recipient blocked bot", extra={"notification_id": n.id})
        except Exception as e:
            n.attempts += 1
            n.last_error = f"{type(e).__name__}: {e}"[:500]
            if n.attempts >= MAX_ATTEMPTS:
                n.status = NotificationStatus.failed
                log.warning("notification failed", extra={"notification_id": n.id})
            else:
                n.send_at = now + retry_delay(n.attempts)
        else:
            n.status = NotificationStatus.sent
    await session.commit()
    return len(rows)


async def run(
    sessionmaker: async_sessionmaker[AsyncSession], sender: Sender, stop: asyncio.Event
) -> None:
    limiter = RateLimiter(MAX_PER_SECOND)
    log.info("worker started")
    while not stop.is_set():
        try:
            while True:
                async with sessionmaker() as session:
                    processed = await process_batch(session, sender, datetime.now(UTC), limiter)
                if processed < BATCH_SIZE or stop.is_set():
                    break
        except Exception:
            log.exception("worker iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=POLL_INTERVAL_SECONDS)
        except TimeoutError:
            pass
    log.info("worker stopped")


async def main() -> None:
    from app.bot.setup import create_bot
    from app.db import SessionLocal, engine
    from app.logging_setup import setup_logging, setup_sentry

    setup_logging()
    setup_sentry()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    bot = create_bot()
    try:
        await run(SessionLocal, TelegramSender(bot), stop)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
