"""Форматирование дат, цен и телефонов для пользовательских текстов."""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS_GEN = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]


def fmt_date(dt: datetime, tz: str) -> str:
    """«пт, 9 октября»"""
    local = dt.astimezone(ZoneInfo(tz))
    return f"{WEEKDAYS[local.weekday()]}, {local.day} {MONTHS_GEN[local.month - 1]}"


def fmt_time(dt: datetime, tz: str) -> str:
    return dt.astimezone(ZoneInfo(tz)).strftime("%H:%M")


def fmt_datetime(dt: datetime, tz: str) -> str:
    """«пт, 9 октября, 14:30»"""
    return f"{fmt_date(dt, tz)}, {fmt_time(dt, tz)}"


def fmt_price(price: int, is_from: bool = False) -> str:
    """«1 500 ₽» / «от 1 500 ₽»"""
    body = f"{price:,}".replace(",", " ") + " ₽"
    return f"от {body}" if is_from else body


def normalize_phone(raw: str) -> str | None:
    """Приводит телефон к E.164. Российские номера 8XXXXXXXXXX / XXXXXXXXXX → +7…"""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] in "78":
        digits = "7" + digits[1:]
    elif len(digits) == 10 and digits[0] == "9":
        digits = "7" + digits
    if not 10 <= len(digits) <= 15:
        return None
    return "+" + digits


def mask_phone(phone: str | None) -> str:
    """+79161234567 → «+7 *** ***-45-67» (для логов)."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 4:
        return "***"
    cc = digits[:-10] if len(digits) > 10 else ""
    return f"+{cc} *** ***-{digits[-4:-2]}-{digits[-2:]}".replace("+ ", "+")
