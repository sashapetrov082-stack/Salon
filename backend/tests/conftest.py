import asyncio
import json
import os
import tempfile
import threading
from collections.abc import AsyncIterator, Iterator
from datetime import date, datetime, time
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

os.environ.setdefault("TEST_DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["BOT_TOKEN"] = "123456:TEST-token"
os.environ["BOT_USERNAME"] = "test_salon_bot"
os.environ["WEBHOOK_SECRET"] = "hook-secret"
os.environ["TELEGRAM_SETUP_ON_STARTUP"] = "false"
os.environ["UPLOADS_DIR"] = tempfile.mkdtemp(prefix="uploads-")
os.environ["UPLOADS_BASE_URL"] = "https://example.ru/uploads/"
os.environ["ADMIN_USERNAME"] = "root"
os.environ["ADMIN_PASSWORD"] = "secret"
os.environ["ENVIRONMENT"] = "test"

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_now
from app.db import Base, SessionLocal
from app.main import app
from app.models import (
    Salon,
    ScheduleBreak,
    Service,
    ServiceCategory,
    Staff,
    StaffRole,
    StaffService,
    User,
    WorkSchedule,
)
from app.services.telegram_auth import compute_hash

TZ = ZoneInfo("Europe/Moscow")
# понедельник, 12 октября 2026, 08:00 по Москве
NOW = datetime(2026, 10, 12, 8, 0, tzinfo=TZ)
TOMORROW = date(2026, 10, 13)
BOT_TOKEN = os.environ["BOT_TOKEN"]


def _migrate() -> None:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "migrations")
    )
    cfg.attributes["configure_logging"] = False
    cfg.attributes["database_url"] = os.environ["DATABASE_URL"]
    command.upgrade(cfg, "head")


async def _reset_schema() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    eng = create_async_engine(os.environ["DATABASE_URL"])
    async with eng.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await eng.dispose()


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    def run() -> None:
        asyncio.run(_reset_schema())
        _migrate()

    t = threading.Thread(target=run)
    t.start()
    t.join()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with SessionLocal() as s:
        await s.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        await s.commit()
        yield s


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Iterator[Clock]:
    c = Clock(NOW)
    app.dependency_overrides[get_now] = c
    yield c
    app.dependency_overrides.pop(get_now, None)


@pytest.fixture
async def http(session: AsyncSession, clock: Clock) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def make_init_data(
    tg_id: int,
    *,
    first_name: str = "Анна",
    last_name: str | None = "Иванова",
    username: str | None = None,
    auth_date: datetime | None = None,
    bot_token: str = BOT_TOKEN,
    extra: dict[str, str] | None = None,
) -> str:
    user: dict[str, Any] = {"id": tg_id, "first_name": first_name, "language_code": "ru"}
    if last_name:
        user["last_name"] = last_name
    if username:
        user["username"] = username
    auth = auth_date or NOW
    fields = {
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(user, ensure_ascii=False, separators=(",", ":")),
        "auth_date": str(int(auth.timestamp())),
        **(extra or {}),
    }
    fields["hash"] = compute_hash(fields, bot_token)
    return urlencode(fields)


def auth(tg_id: int, **kw: Any) -> dict[str, str]:
    return {"Authorization": f"tma {make_init_data(tg_id, **kw)}"}


async def make_user(session: AsyncSession, tg_id: int, first_name: str = "Мастер") -> User:
    user = User(telegram_id=tg_id, first_name=first_name)
    session.add(user)
    await session.flush()
    return user


class SalonFactory:
    """Салон с категорией, услугой и мастерами, работающими пн–вс 10:00–18:00."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def salon(self, slug: str = "beauty", **kw: Any) -> Salon:
        salon = Salon(slug=slug, name=kw.pop("name", "Салон Красоты"), **kw)
        self.session.add(salon)
        await self.session.flush()
        await self.session.refresh(salon)
        return salon

    async def category(self, salon: Salon, name: str = "Стрижки") -> ServiceCategory:
        cat = ServiceCategory(salon_id=salon.id, name=name, sort_order=0)
        self.session.add(cat)
        await self.session.flush()
        return cat

    async def service(
        self,
        salon: Salon,
        category: ServiceCategory,
        name: str = "Стрижка",
        duration: int = 60,
        buffer: int = 0,
        price: int = 1500,
        **kw: Any,
    ) -> Service:
        s = Service(
            salon_id=salon.id,
            category_id=category.id,
            name=name,
            price=price,
            price_is_from=kw.pop("price_is_from", False),
            duration_min=duration,
            buffer_after_min=buffer,
            is_active=kw.pop("is_active", True),
            sort_order=0,
            **kw,
        )
        self.session.add(s)
        await self.session.flush()
        return s

    async def staff(
        self,
        salon: Salon,
        name: str = "Ольга",
        role: StaffRole = StaffRole.master,
        user: User | None = None,
        services: list[Service] | None = None,
        hours: tuple[time, time] | None = (time(10), time(18)),
        sort_order: int = 0,
        **kw: Any,
    ) -> Staff:
        st = Staff(
            salon_id=salon.id,
            user_id=user.id if user else None,
            role=role,
            display_name=name,
            is_bookable=kw.pop("is_bookable", True),
            is_active=kw.pop("is_active", True),
            sort_order=sort_order,
            **kw,
        )
        self.session.add(st)
        await self.session.flush()
        for svc in services or []:
            self.session.add(StaffService(staff_id=st.id, service_id=svc.id))
        if hours:
            for wd in range(7):
                self.session.add(
                    WorkSchedule(staff_id=st.id, weekday=wd, start_time=hours[0], end_time=hours[1])
                )
        await self.session.flush()
        return st

    async def lunch(self, staff: Staff, start: time, end: time) -> None:
        for wd in range(7):
            self.session.add(
                ScheduleBreak(staff_id=staff.id, weekday=wd, start_time=start, end_time=end)
            )
        await self.session.flush()


@pytest.fixture
def factory(session: AsyncSession) -> SalonFactory:
    return SalonFactory(session)


class World:
    salon: Salon
    category: ServiceCategory
    service: Service
    master: Staff
    master_user: User
    master2: Staff
    owner: Staff
    owner_user: User


@pytest.fixture
async def world(session: AsyncSession, factory: SalonFactory) -> World:
    w = World()
    w.salon = await factory.salon()
    w.category = await factory.category(w.salon)
    w.service = await factory.service(w.salon, w.category)
    w.master_user = await make_user(session, 1001, "Ольга")
    w.owner_user = await make_user(session, 1002, "Владелец")
    w.master = await factory.staff(
        w.salon, "Ольга", user=w.master_user, services=[w.service], sort_order=1
    )
    w.master2 = await factory.staff(w.salon, "Ирина", services=[w.service], sort_order=2)
    w.owner = await factory.staff(
        w.salon,
        "Владелец",
        role=StaffRole.owner,
        user=w.owner_user,
        hours=None,
        is_bookable=False,
    )
    await session.commit()
    return w


def at(day: date, h: int, m: int = 0) -> datetime:
    return datetime.combine(day, time(h, m), tzinfo=TZ)


def iso(dt: datetime) -> str:
    return dt.isoformat()
