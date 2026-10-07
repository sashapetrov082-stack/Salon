import time
from datetime import timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, AppointmentSource, Client
from tests.conftest import NOW, SalonFactory, at, auth, make_user


async def test_availability_speed_10_masters_30_days(
    http: httpx.AsyncClient, session: AsyncSession, factory: SalonFactory
) -> None:
    salon = await factory.salon()
    cat = await factory.category(salon)
    service = await factory.service(salon, cat, duration=45, buffer=15)
    user = await make_user(session, 1)
    client = Client(salon_id=salon.id, user_id=user.id, name="X", phone="+70000000000")
    session.add(client)
    staff = [await factory.staff(salon, f"M{i}", services=[service]) for i in range(10)]
    await session.flush()
    # по 5 записей в день у каждого мастера на 30 дней
    for st in staff:
        for d in range(30):
            day = NOW.date() + timedelta(days=d)
            for hour in (10, 12, 13, 15, 17):
                start = at(day, hour)
                session.add(
                    Appointment(
                        salon_id=salon.id,
                        staff_id=st.id,
                        client_id=client.id,
                        service_id=service.id,
                        starts_at=start,
                        ends_at=start + timedelta(minutes=45),
                        blocked_until=start + timedelta(minutes=60),
                        source=AppointmentSource.manual,
                        price=1,
                    )
                )
    await session.commit()
    h = auth(1)
    base = f"/api/salons/{salon.slug}"
    await http.get(f"{base}/availability/days?service_id={service.id}", headers=h)  # прогрев

    timings = {}
    tomorrow = NOW.date() + timedelta(days=1)
    for name, path in {
        "days": f"{base}/availability/days?service_id={service.id}",
        "slots": f"{base}/availability/slots?service_id={service.id}&date={tomorrow}",
        "staff": f"{base}/staff?service_id={service.id}",
    }.items():
        started = time.perf_counter()
        r = await http.get(path, headers=h)
        timings[name] = time.perf_counter() - started
        assert r.status_code == 200
    print(timings)
    assert max(timings.values()) < 0.3, timings
