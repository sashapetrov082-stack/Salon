import io

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, Notification, NotificationKind, NotificationStatus, StaffRole
from tests.conftest import TOMORROW, SalonFactory, World, at, auth, iso, make_user

MASTER = auth(1001)
OWNER = auth(1002)


def url(w: World, path: str) -> str:
    return f"/api/manage/{w.salon.id}{path}"


async def client_booking(http: httpx.AsyncClient, w: World, staff_id: int, h: int = 11) -> dict:
    r = await http.post(
        "/api/salons/beauty/appointments",
        json={
            "service_id": w.service.id,
            "staff_id": staff_id,
            "starts_at": iso(at(TOMORROW, h)),
            "name": "Анна",
            "phone": "+79161234567",
        },
        headers=auth(777),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_access_control(
    http: httpx.AsyncClient, world: World, factory: SalonFactory, session: AsyncSession
) -> None:
    other = await factory.salon("other")
    await session.commit()
    assert (await http.get(url(world, "/calendar"), headers=auth(5555))).status_code == 403
    r = await http.get(f"/api/manage/{other.id}/calendar", headers=OWNER)
    assert r.status_code == 403
    # мастер: только чтение каталога и свои данные
    assert (await http.get(url(world, "/services"), headers=MASTER)).status_code == 200
    r = await http.post(url(world, "/categories"), json={"name": "X"}, headers=MASTER)
    assert r.status_code == 403
    r = await http.get(url(world, f"/staff/{world.master2.id}/schedule"), headers=MASTER)
    assert r.status_code == 403
    assert (await http.patch(url(world, "/settings"), json={}, headers=MASTER)).status_code == 403
    # неактивный сотрудник теряет доступ
    world.master.is_active = False
    await session.commit()
    assert (await http.get(url(world, "/calendar"), headers=MASTER)).status_code == 403


async def test_calendar_master_sees_own(http: httpx.AsyncClient, world: World) -> None:
    await client_booking(http, world, world.master.id, 11)
    await client_booking(http, world, world.master2.id, 12)
    q = "/calendar?from=2026-10-13&to=2026-10-13"
    mine = (await http.get(url(world, q), headers=MASTER)).json()
    assert [a["staff_id"] for a in mine["appointments"]] == [world.master.id]
    assert [s["id"] for s in mine["staff"]] == [world.master.id]
    # мастер не может подсмотреть чужой календарь через staff_id
    other = (await http.get(url(world, q + f"&staff_id={world.master2.id}"), headers=MASTER)).json()
    assert [a["staff_id"] for a in other["appointments"]] == [world.master.id]

    all_ = (await http.get(url(world, q), headers=OWNER)).json()
    assert len(all_["appointments"]) == 2
    assert all_["appointments"][0]["client"]["phone"] == "+79161234567"
    only = (await http.get(url(world, q + f"&staff_id={world.master2.id}"), headers=OWNER)).json()
    assert [a["staff_id"] for a in only["appointments"]] == [world.master2.id]


async def test_status_changes_and_counters(
    http: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    appt = await client_booking(http, world, world.master.id)
    r = await http.patch(
        url(world, f"/appointments/{appt['id']}"), json={"status": "completed"}, headers=MASTER
    )
    assert r.status_code == 200, r.text
    assert r.json()["client"]["visits_count"] == 1
    # исправление: на самом деле не пришёл
    r = await http.patch(
        url(world, f"/appointments/{appt['id']}"), json={"status": "no_show"}, headers=MASTER
    )
    assert r.json()["client"]["visits_count"] == 0
    assert r.json()["client"]["no_show_count"] == 1
    r = await http.patch(
        url(world, f"/appointments/{appt['id']}"),
        json={"status": "cancelled_by_salon"},
        headers=MASTER,
    )
    assert r.json()["error"] == "not_active"
    r = await http.patch(
        url(world, f"/appointments/{appt['id']}"), json={"status": "booked"}, headers=MASTER
    )
    assert r.json()["error"] == "bad_status"
    # напоминания отменены
    pending = (
        (
            await session.execute(
                select(Notification).where(
                    Notification.status == NotificationStatus.pending,
                    Notification.kind.in_(
                        [NotificationKind.reminder_24h, NotificationKind.reminder_2h]
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    assert pending == []


async def test_cancel_by_salon_notifies_client(
    http: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    appt = await client_booking(http, world, world.master2.id)
    # мастер не может менять чужие записи
    r = await http.patch(
        url(world, f"/appointments/{appt['id']}"),
        json={"status": "cancelled_by_salon"},
        headers=MASTER,
    )
    assert r.status_code == 403
    r = await http.patch(
        url(world, f"/appointments/{appt['id']}"),
        json={"status": "cancelled_by_salon"},
        headers=OWNER,
    )
    assert r.json()["status"] == "cancelled_by_salon"
    kinds = {
        n.kind
        for n in (
            await session.execute(
                select(Notification).where(Notification.status == NotificationStatus.pending)
            )
        ).scalars()
    }
    assert kinds == {NotificationKind.client_cancelled_by_salon}


async def test_manual_booking_and_staff_reschedule(
    http: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    body = {
        "staff_id": world.master.id,
        "service_id": world.service.id,
        "starts_at": iso(at(TOMORROW, 9)),  # вне смены — ручная запись допускается
        "client": {"name": "Позвонила", "phone": "8 916 000-11-22"},
    }
    r = await http.post(url(world, "/appointments"), json=body, headers=MASTER)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["source"] == "manual"
    assert created["client"]["phone"] == "+79160001122"
    # клиент без Telegram и действие самого мастера → уведомлений нет
    assert (await session.execute(select(Notification))).scalars().all() == []

    # пересечение запрещено
    body2 = body | {"starts_at": iso(at(TOMORROW, 9, 30)), "client_id": created["client"]["id"]}
    del body2["client"]
    r = await http.post(url(world, "/appointments"), json=body2, headers=MASTER)
    assert r.status_code == 409

    # мастер не может записать к другому мастеру
    r = await http.post(
        url(world, "/appointments"), json=body2 | {"staff_id": world.master2.id}, headers=MASTER
    )
    assert r.status_code == 403
    # админ переносит запись к другому мастеру
    r = await http.patch(
        url(world, f"/appointments/{created['id']}"),
        json={"staff_id": world.master2.id, "starts_at": iso(at(TOMORROW, 15))},
        headers=OWNER,
    )
    assert r.status_code == 200, r.text
    assert r.json()["staff_id"] == world.master2.id
    kinds = [n.kind for n in (await session.execute(select(Notification))).scalars()]
    assert kinds == []  # у Ирины нет Telegram, у клиента тоже

    r = await http.post(url(world, "/appointments"), json=body | {"client": None}, headers=OWNER)
    assert r.status_code == 422


async def test_schedule_overrides_time_off(http: httpx.AsyncClient, world: World) -> None:
    sid = world.master.id
    put = {
        "work": [
            {"weekday": 1, "start_time": "09:00", "end_time": "13:00"},
            {"weekday": 1, "start_time": "15:00", "end_time": "20:00"},
        ],
        "breaks": [{"weekday": 1, "start_time": "11:00", "end_time": "11:30"}],
    }
    r = await http.put(url(world, f"/staff/{sid}/schedule"), json=put, headers=MASTER)
    assert r.status_code == 200, r.text
    assert len(r.json()["work"]) == 2
    bad = {"work": [{"weekday": 1, "start_time": "13:00", "end_time": "09:00"}]}
    assert (
        await http.put(url(world, f"/staff/{sid}/schedule"), json=bad, headers=MASTER)
    ).status_code == 422

    async def slots(day: str) -> list[str]:
        r = await http.get(
            f"/api/salons/beauty/availability/slots?service_id={world.service.id}"
            f"&staff_id={sid}&date={day}",
            headers=auth(777),
        )
        return [s["starts_at"][11:16] for s in r.json()]

    tue = await slots("2026-10-13")
    assert tue[0] == "09:00" and "10:30" not in tue and "11:30" in tue and "13:00" not in tue
    assert await slots("2026-10-14") == []  # среда — не рабочий день по новому шаблону

    r = await http.post(
        url(world, f"/staff/{sid}/overrides"),
        json={"date": "2026-10-14", "start_time": "12:00", "end_time": "14:00"},
        headers=MASTER,
    )
    assert r.status_code == 201
    assert await slots("2026-10-14") == ["12:00", "12:15", "12:30", "12:45", "13:00"]
    r = await http.post(
        url(world, f"/staff/{sid}/overrides"),
        json={"date": "2026-10-13", "is_day_off": True},
        headers=MASTER,
    )
    day_off_id = r.json()["id"]
    assert await slots("2026-10-13") == []
    overrides = (await http.get(url(world, f"/staff/{sid}/overrides"), headers=MASTER)).json()
    assert len(overrides) == 2
    r = await http.delete(url(world, f"/staff/{sid}/overrides/{day_off_id}"), headers=MASTER)
    assert r.json() == {"ok": True}
    assert (await slots("2026-10-13"))[0] == "09:00"

    r = await http.post(
        url(world, f"/staff/{sid}/time-off"),
        json={
            "starts_at": iso(at(TOMORROW, 9)),
            "ends_at": iso(at(TOMORROW, 10)),
            "reason": "Врач",
        },
        headers=MASTER,
    )
    assert r.status_code == 201
    to_id = r.json()["id"]
    assert (await slots("2026-10-13"))[0] == "10:00"
    listed = (await http.get(url(world, f"/staff/{sid}/time-off"), headers=MASTER)).json()
    assert [t["reason"] for t in listed] == ["Врач"]
    cal = (await http.get(url(world, "/calendar?from=2026-10-13"), headers=MASTER)).json()
    assert len(cal["time_off"]) == 1
    await http.delete(url(world, f"/staff/{sid}/time-off/{to_id}"), headers=MASTER)
    assert (await slots("2026-10-13"))[0] == "09:00"
    r = await http.post(
        url(world, f"/staff/{sid}/time-off"),
        json={"starts_at": iso(at(TOMORROW, 10)), "ends_at": iso(at(TOMORROW, 9))},
        headers=MASTER,
    )
    assert r.status_code == 422


async def test_catalog_crud(http: httpx.AsyncClient, world: World) -> None:
    r = await http.post(
        url(world, "/categories"), json={"name": "Ногти", "sort_order": 1}, headers=OWNER
    )
    cat = r.json()
    svc = {
        "category_id": cat["id"],
        "name": "Маникюр",
        "price": 2000,
        "price_is_from": True,
        "duration_min": 90,
        "buffer_after_min": 15,
    }
    r = await http.post(url(world, "/services"), json=svc, headers=OWNER)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    r = await http.put(url(world, f"/services/{sid}"), json=svc | {"price": 2500}, headers=OWNER)
    assert r.json()["price"] == 2500
    r = await http.delete(url(world, f"/categories/{cat['id']}"), headers=OWNER)
    assert r.json()["error"] == "category_not_empty"
    # услуга без мастеров не видна клиентам
    services = (await http.get("/api/salons/beauty/services", headers=auth(777))).json()
    assert all(s["name"] != "Маникюр" for c in services for s in c["services"])
    await http.put(
        url(world, f"/staff/{world.master.id}/services"),
        json=[
            {"service_id": world.service.id},
            {"service_id": sid, "price_override": 3000, "duration_override_min": 120},
        ],
        headers=OWNER,
    )
    services = (await http.get("/api/salons/beauty/services", headers=auth(777))).json()
    assert any(s["name"] == "Маникюр" for c in services for s in c["services"])
    staff = (await http.get(f"/api/salons/beauty/staff?service_id={sid}", headers=auth(777))).json()
    assert staff[0]["price"] == 3000 and staff[0]["duration_min"] == 120
    assert staff[0]["price_is_from"] is True

    assert (await http.delete(url(world, f"/services/{sid}"), headers=OWNER)).json() == {"ok": True}
    assert (await http.delete(url(world, f"/categories/{cat['id']}"), headers=OWNER)).json() == {
        "ok": True
    }
    # услуга с историей записей только выключается
    await client_booking(http, world, world.master.id)
    await http.delete(url(world, f"/services/{world.service.id}"), headers=OWNER)
    listed = (await http.get(url(world, "/services"), headers=OWNER)).json()
    assert [s["is_active"] for s in listed] == [False]
    cats = (await http.get(url(world, "/categories"), headers=MASTER)).json()
    assert [c["name"] for c in cats] == ["Стрижки"]
    r = await http.put(url(world, "/categories/999999"), json={"name": "x"}, headers=OWNER)
    assert r.status_code == 404


async def test_staff_crud_and_invite(
    http: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    r = await http.post(url(world, "/staff"), json={"display_name": "Новенькая"}, headers=OWNER)
    assert r.status_code == 201
    new = r.json()
    assert new["role"] == "master" and new["is_linked"] is False
    r = await http.post(url(world, f"/staff/{new['id']}/invite"), headers=OWNER)
    assert r.status_code == 201
    assert r.json()["url"].startswith("https://t.me/test_salon_bot?start=inv_")
    assert len(r.json()["token"]) == 32
    # привязанному нельзя
    r = await http.post(url(world, f"/staff/{world.master.id}/invite"), headers=OWNER)
    assert r.json()["error"] == "already_linked"

    r = await http.put(
        url(world, f"/staff/{new['id']}"),
        json={"display_name": "Мария", "role": "admin", "sort_order": 5},
        headers=OWNER,
    )
    assert r.json()["role"] == "admin"
    # админ не может назначить владельца
    admin_user = await make_user(session, 4000)
    from app.models import Staff

    st = await session.get(Staff, new["id"])
    assert st is not None
    st.user_id = admin_user.id
    await session.commit()
    r = await http.put(
        url(world, f"/staff/{world.master2.id}"),
        json={"display_name": "Ирина", "role": StaffRole.owner.value},
        headers=auth(4000),
    )
    assert r.status_code == 403
    r = await http.put(
        url(world, f"/staff/{world.owner.id}"),
        json={"display_name": "Владелец", "role": "owner", "is_active": False},
        headers=OWNER,
    )
    assert r.json()["error"] == "self_edit"

    r = await http.delete(url(world, f"/staff/{new['id']}"), headers=OWNER)
    assert r.json() == {"ok": True}
    await client_booking(http, world, world.master2.id)
    await http.delete(url(world, f"/staff/{world.master2.id}"), headers=OWNER)
    listed = (await http.get(url(world, "/staff"), headers=OWNER)).json()
    by_id = {s["id"]: s for s in listed}
    assert by_id[world.master2.id]["is_active"] is False
    assert new["id"] not in by_id
    assert (
        await http.get(url(world, f"/staff/{world.master.id}/services"), headers=MASTER)
    ).status_code == 200


async def test_clients(http: httpx.AsyncClient, world: World, session: AsyncSession) -> None:
    await client_booking(http, world, world.master.id)
    session.add(Client(salon_id=world.salon.id, name="Борис 100%", phone="+79035550000"))
    await session.commit()
    names = lambda r: [c["name"] for c in r.json()]  # noqa: E731
    assert names(await http.get(url(world, "/clients?q=анн"), headers=MASTER)) == ["Анна"]
    assert names(await http.get(url(world, "/clients?q=8916123"), headers=MASTER)) == []
    assert names(await http.get(url(world, "/clients?q=916 123"), headers=MASTER)) == ["Анна"]
    assert names(await http.get(url(world, "/clients?q=100%"), headers=MASTER)) == ["Борис 100%"]
    assert len((await http.get(url(world, "/clients"), headers=MASTER)).json()) == 2

    cid = (await http.get(url(world, "/clients?q=анн"), headers=MASTER)).json()[0]["id"]
    detail = (await http.get(url(world, f"/clients/{cid}"), headers=MASTER)).json()
    assert detail["has_telegram"] is True
    assert detail["appointments"][0]["staff_name"] == "Ольга"
    r = await http.patch(
        url(world, f"/clients/{cid}"), json={"notes": "Аллергия на краску"}, headers=MASTER
    )
    assert r.json()["notes"] == "Аллергия на краску"
    r = await http.patch(url(world, f"/clients/{cid}"), json={"phone": "abc12"}, headers=MASTER)
    assert r.json()["error"] == "invalid_phone"
    assert (await http.get(url(world, "/clients/999999"), headers=MASTER)).status_code == 404


async def test_settings_photos_uploads(http: httpx.AsyncClient, world: World) -> None:
    r = await http.get(url(world, "/settings"), headers=MASTER)
    assert r.json()["booking_link"] == "https://t.me/test_salon_bot?startapp=s_beauty"
    r = await http.patch(
        url(world, "/settings"),
        json={
            "announcement": "Скидки нет, но есть чай",
            "map_url": "https://yandex.ru/maps/-/x",
            "slot_step_min": 30,
            "timezone": "Asia/Yekaterinburg",
        },
        headers=OWNER,
    )
    assert r.status_code == 200, r.text
    assert r.json()["slot_step_min"] == 30
    r = await http.patch(
        url(world, "/settings"), json={"map_url": "javascript:alert(1)"}, headers=OWNER
    )
    assert r.status_code == 422
    r = await http.patch(url(world, "/settings"), json={"timezone": "Mars/Base"}, headers=OWNER)
    assert r.status_code == 422
    r = await http.patch(url(world, "/settings"), json={"name": " "}, headers=OWNER)
    assert r.status_code == 400

    img = Image.new("RGB", (3200, 1600), "red")
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    r = await http.post(
        url(world, "/uploads"),
        files={"file": ("a.jpg", buf.getvalue(), "image/jpeg")},
        headers=OWNER,
    )
    assert r.status_code == 201, r.text
    uploaded = r.json()["url"]
    assert uploaded.startswith(
        f"https://example.ru/uploads/{world.salon.id}/"
    ) and uploaded.endswith(".jpg")
    import os

    from app.config import settings

    saved = os.path.join(settings.uploads_dir, uploaded.removeprefix("https://example.ru/uploads/"))
    assert Image.open(saved).size == (1600, 800)

    r = await http.post(
        url(world, "/uploads"), files={"file": ("a.txt", b"hello", "text/plain")}, headers=OWNER
    )
    assert r.json()["error"] == "bad_image"
    r = await http.post(
        url(world, "/uploads"),
        files={"file": ("a.jpg", b"x" * (5 * 1024 * 1024 + 1), "image/jpeg")},
        headers=OWNER,
    )
    assert r.status_code == 413

    r = await http.post(url(world, "/photos"), json={"url": uploaded}, headers=OWNER)
    pid = r.json()["id"]
    show = (await http.get("/api/salons/beauty", headers=auth(777))).json()
    assert show["photos"][0]["url"] == uploaded
    assert show["announcement"] == "Скидки нет, но есть чай"
    await http.delete(url(world, f"/photos/{pid}"), headers=OWNER)
    assert (await http.get(url(world, "/settings"), headers=OWNER)).json()["photos"] == []


async def test_health_privacy_admin(http: httpx.AsyncClient) -> None:
    assert (await http.get("/health")).json() == {"status": "ok"}
    r = await http.get("/privacy")
    assert "Политика обработки персональных данных" in r.text
    r = await http.get("/admin/", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    r = await http.post(
        "/admin/login", data={"username": "root", "password": "wrong"}, follow_redirects=False
    )
    assert r.status_code == 400
    r = await http.post(
        "/admin/login", data={"username": "root", "password": "secret"}, follow_redirects=False
    )
    assert r.status_code == 302
    r = await http.get("/admin/salon/list")
    assert r.status_code == 200
