from datetime import timedelta
from urllib.parse import parse_qsl, urlencode

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.telegram_auth import InitDataError, validate_init_data
from tests.conftest import BOT_TOKEN, NOW, auth, make_init_data

MAX_AGE = 24 * 3600


def test_valid_signature() -> None:
    data = validate_init_data(
        make_init_data(42, username="anna", extra={"start_param": "s_beauty"}),
        BOT_TOKEN,
        max_age_seconds=MAX_AGE,
        now=NOW,
    )
    assert data.user.id == 42
    assert data.user.first_name == "Анна"
    assert data.user.username == "anna"
    assert data.start_param == "s_beauty"


def test_tampered_field_rejected() -> None:
    fields = dict(parse_qsl(make_init_data(42)))
    fields["user"] = fields["user"].replace("42", "43")
    with pytest.raises(InitDataError):
        validate_init_data(urlencode(fields), BOT_TOKEN, max_age_seconds=MAX_AGE, now=NOW)


def test_wrong_bot_token_rejected() -> None:
    with pytest.raises(InitDataError):
        validate_init_data(
            make_init_data(42, bot_token="999:other"), BOT_TOKEN, max_age_seconds=MAX_AGE, now=NOW
        )


def test_expired_auth_date_rejected() -> None:
    old = make_init_data(42, auth_date=NOW - timedelta(hours=24, minutes=1))
    with pytest.raises(InitDataError):
        validate_init_data(old, BOT_TOKEN, max_age_seconds=MAX_AGE, now=NOW)
    fresh = make_init_data(42, auth_date=NOW - timedelta(hours=23))
    assert validate_init_data(fresh, BOT_TOKEN, max_age_seconds=MAX_AGE, now=NOW).user.id == 42


@pytest.mark.parametrize("bad", ["", "hash=abc", "user=1&auth_date=1"])
def test_garbage_rejected(bad: str) -> None:
    with pytest.raises(InitDataError):
        validate_init_data(bad, BOT_TOKEN, max_age_seconds=MAX_AGE, now=NOW)


async def test_me_creates_user(http: httpx.AsyncClient, session: AsyncSession) -> None:
    r = await http.get("/api/me", headers=auth(555, username="anna"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["telegram_id"] == 555
    assert body["is_staff"] is False
    user = (await session.execute(select(User).where(User.telegram_id == 555))).scalar_one()
    assert user.username == "anna"

    # повторный запрос обновляет данные, не создавая дубликат
    r = await http.get("/api/me", headers=auth(555, first_name="Аня"))
    assert r.json()["first_name"] == "Аня"
    users = (await session.execute(select(User).where(User.telegram_id == 555))).scalars().all()
    assert len(users) == 1


async def test_me_requires_auth(http: httpx.AsyncClient) -> None:
    r = await http.get("/api/me")
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"
    r = await http.get("/api/me", headers={"Authorization": "tma garbage"})
    assert r.status_code == 401
    r = await http.get("/api/me", headers=auth(1, auth_date=NOW - timedelta(days=2)))
    assert r.status_code == 401
