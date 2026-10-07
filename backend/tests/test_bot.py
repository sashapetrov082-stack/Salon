from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models import Appointment, AppointmentStatus, Staff, StaffInvite, UserContact
from app.services import invites
from tests.conftest import TOMORROW, World, at, auth, iso
from tests.mock_bot import MockSession

HEADERS = {"X-Telegram-Bot-Api-Secret-Token": "hook-secret"}


@pytest.fixture
def tg() -> Iterator[MockSession]:
    bot = app.state.bot
    original = bot.session
    mock = MockSession()
    bot.session = mock
    yield mock
    bot.session = original


def _from(tg_id: int) -> dict:
    return {"id": tg_id, "is_bot": False, "first_name": "Пётр", "username": "petr"}


def message_update(tg_id: int, **message: object) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "date": int(datetime.now(UTC).timestamp()),
            "chat": {"id": tg_id, "type": "private"},
            "from": _from(tg_id),
            **message,
        },
    }


async def post_update(http: httpx.AsyncClient, update: dict) -> httpx.Response:
    return await http.post("/tg/webhook/hook-secret", json=update, headers=HEADERS)


async def test_webhook_secret_checked(http: httpx.AsyncClient, tg: MockSession) -> None:
    upd = message_update(5, text="/start")
    r = await http.post("/tg/webhook/hook-secret", json=upd)
    assert r.status_code == 403
    r = await http.post("/tg/webhook/wrong", json=upd, headers=HEADERS)
    assert r.status_code == 403
    assert tg.calls == []


async def test_start_greets(http: httpx.AsyncClient, tg: MockSession) -> None:
    r = await post_update(http, message_update(5, text="/start"))
    assert r.status_code == 200
    (msg,) = tg.of("SendMessage")
    assert "Здравствуйте" in msg.text
    assert msg.reply_markup.inline_keyboard[0][0].web_app.url == "https://example.ru/app/"


async def test_start_invite_links_staff(
    http: httpx.AsyncClient, tg: MockSession, world: World, session: AsyncSession
) -> None:
    invite = await invites.create_invite(session, world.master2, datetime.now(UTC))
    await session.commit()
    r = await post_update(http, message_update(6000, text=f"/start inv_{invite.token}"))
    assert r.status_code == 200
    (msg,) = tg.of("SendMessage")
    assert "Вы добавлены в салон «Салон Красоты»" in msg.text
    assert msg.reply_markup.inline_keyboard[0][0].web_app.url.endswith(
        f"startapp=m_{world.salon.id}"
    )
    staff = (
        await session.execute(
            select(Staff)
            .where(Staff.id == world.master2.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert staff.user_id is not None

    me = (await http.get("/api/me", headers=auth(6000))).json()
    assert me["is_staff"] is True
    assert me["staff_salons"][0]["salon_id"] == world.salon.id

    # повторное использование
    tg.calls.clear()
    await post_update(http, message_update(6001, text=f"/start inv_{invite.token}"))
    assert "уже использовано" in tg.of("SendMessage")[0].text


async def test_invite_expired_and_unknown(world: World, session: AsyncSession) -> None:
    now = datetime.now(UTC)
    invite = await invites.create_invite(session, world.master2, now)
    await session.commit()
    from app.errors import AppError
    from tests.conftest import make_user

    user = await make_user(session, 6100)
    with pytest.raises(AppError) as e:
        await invites.accept_invite(session, invite.token, user, now + timedelta(days=8))
    assert e.value.code == "invite_expired"
    with pytest.raises(AppError) as e:
        await invites.accept_invite(session, "x" * 32, user, now)
    assert e.value.code == "invite_not_found"
    # уже привязанному сотруднику приглашение не создаётся
    with pytest.raises(AppError):
        await invites.create_invite(session, world.master, now)
    # пользователь уже сотрудник салона
    with pytest.raises(AppError) as e:
        await invites.accept_invite(session, invite.token, world.master_user, now)
    assert e.value.code == "already_in_salon"
    assert len(invites.new_token()) == 32
    rows = (await session.execute(select(StaffInvite))).scalars().all()
    assert all(r.used_at is None for r in rows)


async def test_contact_saved_only_own(
    http: httpx.AsyncClient, tg: MockSession, session: AsyncSession
) -> None:
    foreign = {"phone_number": "79160000000", "first_name": "Чужой", "user_id": 999}
    await post_update(http, message_update(7000, contact=foreign))
    assert (await session.execute(select(UserContact))).scalars().all() == []
    assert "свой контакт" in tg.of("SendMessage")[0].text

    own = {"phone_number": "79161112233", "first_name": "Пётр", "user_id": 7000}
    await post_update(http, message_update(7000, contact=own))
    contact = (await session.execute(select(UserContact))).scalar_one()
    assert contact.phone == "+79161112233"
    r = await http.get("/api/me/contact-status", headers=auth(7000))
    assert r.json() == {"received": True, "phone": "+79161112233"}


async def test_confirm_callback(
    http: httpx.AsyncClient, tg: MockSession, world: World, session: AsyncSession
) -> None:
    r = await http.post(
        "/api/salons/beauty/appointments",
        json={
            "service_id": world.service.id,
            "staff_id": world.master.id,
            "starts_at": iso(at(TOMORROW, 11)),
            "name": "Пётр",
            "phone": "+79161112233",
        },
        headers=auth(7000),
    )
    appt_id = r.json()["id"]

    def callback(user_id: int) -> dict:
        return {
            "update_id": 2,
            "callback_query": {
                "id": "cb1",
                "from": _from(user_id),
                "chat_instance": "ci",
                "data": f"ap:c:{appt_id}",
                "message": {
                    "message_id": 11,
                    "date": int(datetime.now(UTC).timestamp()),
                    "chat": {"id": user_id, "type": "private"},
                    "text": "⏰ Напоминаем: завтра у вас запись",
                },
            },
        }

    # чужая запись
    await post_update(http, callback(7001))
    (answer,) = tg.of("AnswerCallbackQuery")
    assert answer.show_alert is True
    tg.calls.clear()

    await post_update(http, callback(7000))
    assert tg.of("AnswerCallbackQuery")[0].text == "Спасибо, ждём вас!"
    (edit,) = tg.of("EditMessageText")
    assert "Вы подтвердили визит" in edit.text
    buttons = [b.text for row in edit.reply_markup.inline_keyboard for b in row]
    assert "✅ Приду" not in buttons and "🔁 Перенести" in buttons
    appt = (
        await session.execute(
            select(Appointment)
            .where(Appointment.id == appt_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert appt.status == AppointmentStatus.confirmed
