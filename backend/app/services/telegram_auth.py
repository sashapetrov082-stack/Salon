"""Проверка initData Telegram Mini App."""

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl


class InitDataError(Exception):
    pass


@dataclass(frozen=True)
class TelegramWebAppUser:
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None


@dataclass(frozen=True)
class InitData:
    user: TelegramWebAppUser
    auth_date: datetime
    start_param: str | None
    raw: dict[str, str]


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def compute_hash(fields: dict[str, str], bot_token: str) -> str:
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields) if k != "hash")
    return hmac.new(_secret_key(bot_token), data_check_string.encode(), hashlib.sha256).hexdigest()


def validate_init_data(
    init_data: str, bot_token: str, *, max_age_seconds: int, now: datetime | None = None
) -> InitData:
    if not init_data or not bot_token:
        raise InitDataError("empty init data")
    fields = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received_hash = fields.get("hash")
    if not received_hash:
        raise InitDataError("hash is missing")
    if not hmac.compare_digest(compute_hash(fields, bot_token), received_hash):
        raise InitDataError("invalid signature")

    try:
        auth_date = datetime.fromtimestamp(int(fields["auth_date"]), tz=UTC)
    except (KeyError, ValueError) as e:
        raise InitDataError("invalid auth_date") from e
    now = now or datetime.now(UTC)
    if (now - auth_date).total_seconds() > max_age_seconds:
        raise InitDataError("init data expired")

    try:
        user_raw: dict[str, Any] = json.loads(fields["user"])
        user = TelegramWebAppUser(
            id=int(user_raw["id"]),
            first_name=user_raw.get("first_name"),
            last_name=user_raw.get("last_name"),
            username=user_raw.get("username"),
            language_code=user_raw.get("language_code"),
        )
    except (KeyError, ValueError, TypeError) as e:
        raise InitDataError("invalid user") from e

    return InitData(
        user=user, auth_date=auth_date, start_param=fields.get("start_param"), raw=fields
    )
