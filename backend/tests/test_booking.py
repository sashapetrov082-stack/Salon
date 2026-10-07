import asyncio
from datetime import datetime, time, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models import (
    Appointment,
    AppointmentStatus,
    Client,
    Notification,
    NotificationKind,
    NotificationStatus,
    TimeOff,
    UserContact,
)
from tests.conftest import NOW, TOMORROW, Clock, SalonFactory, World, at, auth, iso, make_user

CLIENT_TG = 777


def booking_body(w: World, starts_at: str, staff_id: int | None = None, **kw: Any) -> dict:
    body: dict[str, object] = {
        "service_id": w.service.id,
        "staff_id": staff_id if staff_id is not None else w.master.id,
        "starts_at": starts_at,
        "name": "Анна",
        "phone": "8 (916) 123-45-67",
    }
    body.update(kw)
    return body


async def book(
    http: httpx.AsyncClient, w: World, starts_at: str, tg: int = CLIENT_TG, **kw: Any
) -> httpx.Response:
    return await http.post(
        f"/api/salons/{w.salon.slug}/appointments",
        json=booking_body(w, starts_at, **kw),
        headers=auth(tg),
    )


async def test_showcase_services_staff(http: httpx.AsyncClient, world: World) -> None:
    h = auth(CLIENT_TG)
    r = await http.get("/api/salons/beauty", headers=h)
    assert r.status_code == 200
    assert r.json()["name"] == "Салон Красоты"
    assert r.json()["client"] is None

    r = await http.get("/api/salons/beauty/services", headers=h)
    cats = r.json()
    assert cats[0]["name"] == "Стрижки"
    assert cats[0]["services"][0]["price"] == 1500

    r = await http.get(f"/api/salons/beauty/staff?service_id={world.service.id}", headers=h)
    staff = r.json()
    assert [s["display_name"] for s in staff] == ["Ольга", "Ирина"]  # владелец не bookable
    # сейчас 08:00, min lead 60 мин, смена с 10:00 → ближайшее сегодня в 10:00
    assert staff[0]["nearest_slot"].startswith("2026-10-12T10:00")
    assert staff[0]["price"] == 1500

    r = await http.get("/api/salons/nope", headers=h)
    assert r.status_code == 404
    assert r.json() == {"error": "not_found", "message": "Салон не найден"}


async def test_availability_days_and_slots(
    http: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    session.add(
        TimeOff(
            staff_id=world.master.id,
            starts_at=at(TOMORROW, 0),
            ends_at=at(TOMORROW + timedelta(days=1), 0),
        )
    )
    await session.commit()
    h = auth(CLIENT_TG)
    r = await http.get(
        f"/api/salons/beauty/availability/days?service_id={world.service.id}"
        f"&staff_id={world.master.id}&from=2026-10-12&to=2026-10-14",
        headers=h,
    )
    assert r.json() == [
        {"date": "2026-10-12", "has_slots": True},
        {"date": "2026-10-13", "has_slots": False},
        {"date": "2026-10-14", "has_slots": True},
    ]
    # любой мастер: завтра работает Ирина
    r = await http.get(
        f"/api/salons/beauty/availability/slots?service_id={world.service.id}&date=2026-10-13",
        headers=h,
    )
    slots = r.json()
    assert slots[0]["starts_at"].startswith("2026-10-13T10:00")
    assert {s["staff_id"] for s in slots} == {world.master2.id}


async def test_create_appointment(
    http: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    r = await book(http, world, iso(at(TOMORROW, 11)), comment=" Без спешки ")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "booked"
    assert body["staff"]["display_name"] == "Ольга"
    assert body["comment"] == "Без спешки"
    assert body["can_change"] is True

    client = (await session.execute(select(Client))).scalar_one()
    assert client.phone == "+79161234567"
    assert client.name == "Анна"

    kinds = {n.kind: n for n in (await session.execute(select(Notification))).scalars()}
    assert set(kinds) == {
        NotificationKind.client_booked,
        NotificationKind.reminder_24h,
        NotificationKind.reminder_2h,
        NotificationKind.staff_new,
    }
    assert kinds[NotificationKind.reminder_24h].send_at == at(TOMORROW, 11) - timedelta(hours=24)

    # слот исчез из доступных
    r = await http.get(
        f"/api/salons/beauty/availability/slots?service_id={world.service.id}"
        f"&staff_id={world.master.id}&date=2026-10-13",
        headers=auth(CLIENT_TG),
    )
    times = [s["starts_at"][11:16] for s in r.json()]
    assert "11:00" not in times and "10:15" not in times and "12:00" in times

    # витрина знает телефон клиента
    r = await http.get("/api/salons/beauty", headers=auth(CLIENT_TG))
    assert r.json()["client"] == {"name": "Анна", "phone": "+79161234567"}


async def test_reminder_not_created_in_past(
    http: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    r = await book(http, world, iso(at(NOW.date(), 12)))
    assert r.status_code == 201
    kinds = {n.kind for n in (await session.execute(select(Notification))).scalars()}
    assert NotificationKind.reminder_24h not in kinds
    assert NotificationKind.reminder_2h in kinds


async def test_slot_taken_and_validation(http: httpx.AsyncClient, world: World) -> None:
    assert (await book(http, world, iso(at(TOMORROW, 11)))).status_code == 201
    r = await book(http, world, iso(at(TOMORROW, 11, 30)), tg=778)
    assert r.status_code == 409
    assert r.json()["error"] == "slot_taken"
    # не на сетке
    r = await book(http, world, iso(at(TOMORROW, 12, 5)), tg=778)
    assert r.status_code == 409
    # слишком рано (min_lead_time)
    r = await book(http, world, iso(at(NOW.date(), 8, 30)), tg=778)
    assert r.status_code == 409
    # без телефона и без контакта
    r = await book(http, world, iso(at(TOMORROW, 14)), tg=779, phone=None)
    assert r.status_code == 400
    assert r.json()["error"] == "phone_required"
    r = await book(http, world, iso(at(TOMORROW, 14)), tg=779, phone="12")
    assert r.json()["error"] == "invalid_phone"
    # время без часового пояса
    r = await book(http, world, "2026-10-13T14:00:00", tg=779)
    assert r.status_code == 422


async def test_phone_from_telegram_contact(
    http: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    r = await http.get("/api/me/contact-status", headers=auth(CLIENT_TG))
    assert r.json() == {"received": False, "phone": None}
    user = (await http.get("/api/me", headers=auth(CLIENT_TG))).json()
    session.add(UserContact(user_id=user["id"], phone="+79990001122"))
    await session.commit()
    r = await http.get("/api/me/contact-status", headers=auth(CLIENT_TG))
    assert r.json() == {"received": True, "phone": "+79990001122"}
    r = await book(http, world, iso(at(TOMORROW, 11)), phone=None)
    assert r.status_code == 201
    client = (await session.execute(select(Client))).scalar_one()
    assert client.phone == "+79990001122"


async def test_any_master_picks_least_busy(
    http: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    # у Ольги (sort_order=1) уже есть запись завтра → «любой» выберет Ирину
    assert (await book(http, world, iso(at(TOMORROW, 15)), tg=900)).status_code == 201
    r = await http.post(
        "/api/salons/beauty/appointments",
        json=booking_body(world, iso(at(TOMORROW, 11)), staff_id=None) | {"staff_id": None},
        headers=auth(901),
    )
    assert r.status_code == 201, r.text
    assert r.json()["staff"]["id"] == world.master2.id
    # равное число записей → по sort_order (Ольга)
    r = await http.post(
        "/api/salons/beauty/appointments",
        json=booking_body(world, iso(at(TOMORROW + timedelta(days=1), 11))) | {"staff_id": None},
        headers=auth(902),
    )
    assert r.json()["staff"]["id"] == world.master.id


async def test_inactive_entities_rejected(
    http: httpx.AsyncClient, world: World, session: AsyncSession, factory: SalonFactory
) -> None:
    other = await factory.service(world.salon, world.category, name="Окрашивание")
    await session.commit()
    r = await http.post(
        "/api/salons/beauty/appointments",
        json=booking_body(world, iso(at(TOMORROW, 11))) | {"service_id": other.id},
        headers=auth(CLIENT_TG),
    )
    assert r.status_code == 400
    assert r.json()["error"] == "staff_unavailable"

    world.master.is_active = False
    await session.commit()
    r = await book(http, world, iso(at(TOMORROW, 11)))
    assert r.json()["error"] == "staff_unavailable"

    world.service.is_active = False
    await session.commit()
    r = await book(http, world, iso(at(TOMORROW, 11)))
    assert r.status_code == 404

    world.service.is_active = True
    world.salon.is_active = False
    await session.commit()
    r = await book(http, world, iso(at(TOMORROW, 11)), staff_id=world.master2.id)
    assert r.json()["error"] == "salon_inactive"


async def test_max_three_active_appointments(http: httpx.AsyncClient, world: World) -> None:
    for h in (10, 12, 14):
        assert (await book(http, world, iso(at(TOMORROW, h)))).status_code == 201
    r = await book(http, world, iso(at(TOMORROW, 16)))
    assert r.status_code == 400
    assert r.json()["error"] == "too_many_appointments"


async def test_concurrent_booking_one_wins(http: httpx.AsyncClient, world: World) -> None:
    starts = iso(at(TOMORROW, 11))
    results = await asyncio.gather(*(book(http, world, starts, tg=5000 + i) for i in range(10)))
    codes = sorted(r.status_code for r in results)
    assert codes.count(201) == 1, [r.text for r in results]
    assert codes.count(409) == 9
    async with SessionLocal() as s:
        count = (await s.execute(select(func.count()).select_from(Appointment))).scalar_one()
    assert count == 1


async def test_concurrent_booking_same_user(http: httpx.AsyncClient, world: World) -> None:
    starts = iso(at(TOMORROW, 11))
    results = await asyncio.gather(*(book(http, world, starts) for _ in range(10)))
    codes = sorted(r.status_code for r in results)
    assert codes.count(201) == 1
    assert codes.count(409) == 9


async def test_my_appointments_cancel_and_deadline(
    http: httpx.AsyncClient, world: World, session: AsyncSession, clock: Clock
) -> None:
    appt = (await book(http, world, iso(at(TOMORROW, 11)))).json()
    late = (await book(http, world, iso(at(NOW.date(), 10)))).json()  # через 2 ч, дедлайн 3 ч
    assert late["can_change"] is False

    r = await http.get("/api/me/appointments", headers=auth(CLIENT_TG))
    assert [a["id"] for a in r.json()] == [late["id"], appt["id"]]

    r = await http.post(f"/api/me/appointments/{late['id']}/cancel", headers=auth(CLIENT_TG))
    assert r.status_code == 400
    assert r.json()["error"] == "deadline_passed"

    # чужую запись отменить нельзя
    r = await http.post(f"/api/me/appointments/{appt['id']}/cancel", headers=auth(4242))
    assert r.status_code == 404

    r = await http.post(f"/api/me/appointments/{appt['id']}/cancel", headers=auth(CLIENT_TG))
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled_by_client"

    notes = (
        (
            await session.execute(
                select(Notification).where(Notification.appointment_id == appt["id"])
            )
        )
        .scalars()
        .all()
    )
    pending = [n for n in notes if n.status == NotificationStatus.pending]
    assert [n.kind for n in pending] == [NotificationKind.staff_cancelled]

    r = await http.get("/api/me/appointments?scope=past", headers=auth(CLIENT_TG))
    assert [a["id"] for a in r.json()] == [appt["id"]]

    # отменённое время снова свободно
    assert (await book(http, world, iso(at(TOMORROW, 11)), tg=31337)).status_code == 201


async def test_reschedule_recreates_notifications(
    http: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    appt = (await book(http, world, iso(at(TOMORROW, 11)))).json()
    before = (
        (
            await session.execute(
                select(Notification).where(Notification.appointment_id == appt["id"])
            )
        )
        .scalars()
        .all()
    )
    old_ids = {n.id for n in before}

    # перенос на 30 минут: собственная запись не мешает
    new_start = at(TOMORROW + timedelta(days=1), 11, 30)
    r = await http.get(
        f"/api/salons/beauty/availability/slots?service_id={world.service.id}"
        f"&staff_id={world.master.id}&date=2026-10-13&appointment_id={appt['id']}",
        headers=auth(CLIENT_TG),
    )
    assert any(s["starts_at"].startswith("2026-10-13T11:30") for s in r.json())

    r = await http.post(
        f"/api/me/appointments/{appt['id']}/reschedule",
        json={"starts_at": iso(new_start)},
        headers=auth(CLIENT_TG),
    )
    assert r.status_code == 200, r.text
    assert datetime.fromisoformat(r.json()["starts_at"]) == new_start
    assert r.json()["staff"]["id"] == world.master.id

    notes = (
        (
            await session.execute(
                select(Notification)
                .where(Notification.appointment_id == appt["id"])
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    old = [n for n in notes if n.id in old_ids]
    new = [n for n in notes if n.id not in old_ids]
    assert all(n.status == NotificationStatus.cancelled for n in old)
    reminders = {n.kind: n.send_at for n in new if n.kind.value.startswith("reminder")}
    assert reminders == {
        NotificationKind.reminder_24h: new_start - timedelta(hours=24),
        NotificationKind.reminder_2h: new_start - timedelta(hours=2),
    }
    assert NotificationKind.staff_rescheduled in {n.kind for n in new}

    # на занятое время перенести нельзя
    other = (await book(http, world, iso(at(TOMORROW, 15)), tg=999)).json()
    r = await http.post(
        f"/api/me/appointments/{other['id']}/reschedule",
        json={"starts_at": iso(at(TOMORROW + timedelta(days=1), 12))},
        headers=auth(999),
    )
    assert r.status_code == 409


async def test_confirm(http: httpx.AsyncClient, world: World) -> None:
    appt = (await book(http, world, iso(at(TOMORROW, 11)))).json()
    r = await http.post(f"/api/me/appointments/{appt['id']}/confirm", headers=auth(CLIENT_TG))
    assert r.json()["status"] == "confirmed"
    r = await http.post(f"/api/me/appointments/{appt['id']}/confirm", headers=auth(CLIENT_TG))
    assert r.json()["status"] == "confirmed"
    # подтверждённая запись по-прежнему блокирует время
    assert (await book(http, world, iso(at(TOMORROW, 11)), tg=1234)).status_code == 409


async def test_db_constraint_blocks_overlap(session: AsyncSession, world: World) -> None:
    from app.models import AppointmentSource

    user = await make_user(session, 31)
    client = Client(salon_id=world.salon.id, user_id=user.id, name="X", phone="+70000000000")
    session.add(client)
    await session.flush()

    def mk(h: int, m: int = 0, status: AppointmentStatus = AppointmentStatus.booked) -> Appointment:
        start = at(TOMORROW, h, m)
        return Appointment(
            salon_id=world.salon.id,
            staff_id=world.master.id,
            client_id=client.id,
            service_id=world.service.id,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            blocked_until=start + timedelta(hours=1, minutes=15),
            status=status,
            source=AppointmentSource.manual,
            price=1,
        )

    session.add(mk(10))
    session.add(mk(10, 30, AppointmentStatus.cancelled_by_client))  # отменённые не мешают
    await session.commit()
    session.add(mk(11, 15))  # ровно после буфера — можно
    await session.commit()
    from sqlalchemy.exc import IntegrityError

    session.add(mk(11))
    try:
        await session.commit()
    except IntegrityError as e:
        assert "appointment_no_overlap" in str(e)
        await session.rollback()
    else:
        raise AssertionError("overlap was allowed")


async def test_lunch_break_respected(
    http: httpx.AsyncClient, world: World, factory: SalonFactory, session: AsyncSession
) -> None:
    await factory.lunch(world.master, time(13), time(14))
    await session.commit()
    r = await book(http, world, iso(at(TOMORROW, 12, 30)))
    assert r.status_code == 409
    assert (await book(http, world, iso(at(TOMORROW, 12)))).status_code == 201
