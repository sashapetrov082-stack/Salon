from datetime import timedelta

import httpx
import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Appointment,
    AppointmentStatus,
    Notification,
    NotificationKind,
    NotificationStatus,
    User,
)
from app.worker import (
    MAX_ATTEMPTS,
    RateLimiter,
    RecipientBlocked,
    TelegramSender,
    process_batch,
    retry_delay,
)
from tests.conftest import NOW, TOMORROW, World, at, auth, iso
from tests.mock_bot import MockSession


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[tuple[int, NotificationKind, int]] = []
        self.error: Exception | None = None

    async def send(self, chat_id: int, kind: NotificationKind, appt: Appointment) -> None:
        if self.error is not None:
            raise self.error
        self.sent.append((chat_id, kind, appt.id))


async def _book(http: httpx.AsyncClient, w: World, tg: int = 777) -> dict:
    r = await http.post(
        "/api/salons/beauty/appointments",
        json={
            "service_id": w.service.id,
            "staff_id": w.master.id,
            "starts_at": iso(at(TOMORROW, 11)),
            "name": "Анна",
            "phone": "+79161234567",
        },
        headers=auth(tg),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _notes(session: AsyncSession) -> list[Notification]:
    return list(
        (
            await session.execute(
                select(Notification)
                .order_by(Notification.id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )


async def test_sends_due_and_keeps_future(
    http: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    await _book(http, world)
    sender = FakeSender()
    assert await process_batch(session, sender, NOW) == 2
    kinds = sorted(k.value for _, k, _ in sender.sent)
    assert kinds == ["client_booked", "staff_new"]
    assert {chat for chat, _, _ in sender.sent} == {777, 1001}

    notes = await _notes(session)
    by_kind = {n.kind: n for n in notes}
    assert by_kind[NotificationKind.client_booked].status == NotificationStatus.sent
    assert by_kind[NotificationKind.reminder_24h].status == NotificationStatus.pending

    # через сутки уходит напоминание за 24 ч
    assert await process_batch(session, sender, at(TOMORROW, 11) - timedelta(hours=23)) == 1
    assert sender.sent[-1][1] == NotificationKind.reminder_24h


async def test_inactive_appointment_reminder_cancelled(
    http: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    appt = await _book(http, world)
    sender = FakeSender()
    await process_batch(session, sender, NOW)
    # салон отменил запись в обход API, напоминание уже в очереди
    row = await session.get(Appointment, appt["id"])
    assert row is not None
    row.status = AppointmentStatus.cancelled_by_salon
    await session.commit()
    await process_batch(session, sender, at(TOMORROW, 10))
    statuses = {n.kind: n.status for n in await _notes(session)}
    assert statuses[NotificationKind.reminder_24h] == NotificationStatus.cancelled
    assert statuses[NotificationKind.reminder_2h] == NotificationStatus.cancelled
    assert len(sender.sent) == 2


async def test_staff_cancelled_sent_for_cancelled_appointment(
    http: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    appt = await _book(http, world)
    await http.post(f"/api/me/appointments/{appt['id']}/cancel", headers=auth(777))
    sender = FakeSender()
    await process_batch(session, sender, NOW)
    assert [k for _, k, _ in sender.sent] == [NotificationKind.staff_cancelled]


async def test_blocked_recipient(
    http: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    await _book(http, world)
    sender = FakeSender()
    sender.error = RecipientBlocked("Forbidden: bot was blocked by the user")
    await process_batch(session, sender, NOW)
    notes = [n for n in await _notes(session) if n.send_at <= NOW]
    assert all(n.status == NotificationStatus.failed for n in notes)
    assert all(n.attempts == 0 for n in notes)
    users = (
        await session.execute(select(User).execution_options(populate_existing=True))
    ).scalars()
    assert all(u.bot_blocked for u in users if u.telegram_id in (777, 1001))

    # дальнейшие уведомления заблокировавшему не отправляются
    sender.error = None
    await process_batch(session, sender, at(TOMORROW, 10))
    assert sender.sent == []


async def test_retry_with_backoff_then_fail(
    http: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    await _book(http, world)
    sender = FakeSender()
    sender.error = RuntimeError("network down")
    now = NOW
    await process_batch(session, sender, now)
    n = next(n for n in await _notes(session) if n.kind == NotificationKind.client_booked)
    assert n.status == NotificationStatus.pending
    assert n.attempts == 1
    assert n.send_at == now + timedelta(minutes=2)
    assert "network down" in (n.last_error or "")

    for attempt in range(2, MAX_ATTEMPTS + 1):
        now = now + retry_delay(attempt - 1)
        await process_batch(session, sender, now)
    n = next(n for n in await _notes(session) if n.kind == NotificationKind.client_booked)
    assert n.attempts == MAX_ATTEMPTS
    assert n.status == NotificationStatus.failed


async def test_telegram_sender_renders_all_kinds(
    http: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    world.salon.address = "ул. Ленина, 1"
    world.salon.map_url = "https://yandex.ru/maps/-/abc"
    world.salon.phone = "+74950000000"
    await session.commit()
    appt_id = (await _book(http, world))["id"]
    from sqlalchemy.orm import selectinload

    appt = await session.get(
        Appointment,
        appt_id,
        options=[
            selectinload(Appointment.salon),
            selectinload(Appointment.service),
            selectinload(Appointment.staff),
            selectinload(Appointment.client),
        ],
    )
    assert appt is not None
    mock = MockSession()
    bot = Bot("123:abc", session=mock)
    sender = TelegramSender(bot)
    for kind in NotificationKind:
        await sender.send(777, kind, appt)
    msgs: list[SendMessage] = mock.of("SendMessage")
    texts = {k: m for k, m in zip(NotificationKind, msgs, strict=True)}
    reminder = texts[NotificationKind.reminder_24h]
    assert "завтра" in reminder.text
    assert "вт, 13 октября, 11:00" in reminder.text
    assert "ул. Ленина, 1" in reminder.text
    buttons = [b for row in reminder.reply_markup.inline_keyboard for b in row]  # type: ignore[union-attr]
    assert buttons[0].callback_data == f"ap:c:{appt_id}"
    assert buttons[1].web_app is not None and buttons[1].web_app.url.endswith(
        f"startapp=r_{appt_id}"
    )
    assert buttons[2].url == "https://yandex.ru/maps/-/abc"
    staff_new = texts[NotificationKind.staff_new]
    assert "+79161234567" in staff_new.text and "Анна" in staff_new.text
    assert "1\u00a0500\u00a0₽" in texts[NotificationKind.client_booked].text
    assert "+74950000000" in texts[NotificationKind.client_cancelled_by_salon].text

    mock.fail_with = TelegramForbiddenError(method=msgs[0], message="Forbidden: bot was blocked")
    with pytest.raises(RecipientBlocked):
        await sender.send(777, NotificationKind.client_booked, appt)


async def test_rate_limiter_spacing() -> None:
    import time

    limiter = RateLimiter(25)
    start = time.monotonic()
    for _ in range(6):
        await limiter.wait()
    assert time.monotonic() - start >= 5 / 25 - 0.01
