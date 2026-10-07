"""Приглашения сотрудников по ссылке t.me/<bot>?start=inv_<token>."""

import secrets
import string
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import AppError
from app.models import Salon, Staff, StaffInvite, User

TOKEN_ALPHABET = string.ascii_letters + string.digits


def new_token() -> str:
    return "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(32))


async def create_invite(session: AsyncSession, staff: Staff, now: datetime) -> StaffInvite:
    if staff.user_id is not None:
        raise AppError("already_linked", "Сотрудник уже привязан к Telegram")
    invite = StaffInvite(
        salon_id=staff.salon_id,
        staff_id=staff.id,
        token=new_token(),
        expires_at=now + timedelta(days=settings.invite_ttl_days),
    )
    session.add(invite)
    await session.flush()
    return invite


async def accept_invite(
    session: AsyncSession, token: str, user: User, now: datetime
) -> tuple[Staff, Salon]:
    invite = (
        await session.execute(
            select(StaffInvite).where(StaffInvite.token == token).with_for_update()
        )
    ).scalar_one_or_none()
    if invite is None:
        raise AppError("invite_not_found", "Приглашение не найдено")
    if invite.used_at is not None:
        raise AppError("invite_used", "Это приглашение уже использовано")
    if invite.expires_at <= now:
        raise AppError("invite_expired", "Срок действия приглашения истёк. Попросите новое.")

    staff = await session.get(Staff, invite.staff_id, with_for_update=True)
    salon = await session.get(Salon, invite.salon_id)
    if staff is None or salon is None or not staff.is_active:
        raise AppError("invite_not_found", "Приглашение не найдено")
    if staff.user_id is not None and staff.user_id != user.id:
        raise AppError("invite_used", "Это приглашение уже использовано")
    other = (
        await session.execute(
            select(Staff).where(
                Staff.salon_id == salon.id, Staff.user_id == user.id, Staff.id != staff.id
            )
        )
    ).scalar_one_or_none()
    if other is not None:
        raise AppError("already_in_salon", f"Вы уже сотрудник салона «{salon.name}»")

    staff.user_id = user.id
    invite.used_at = now
    await session.commit()
    return staff, salon
