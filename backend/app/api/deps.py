from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.errors import Forbidden, NotFound, Unauthorized
from app.models import ADMIN_ROLES, Salon, Staff, StaffRole, User
from app.services.telegram_auth import InitDataError, TelegramWebAppUser, validate_init_data

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_now() -> datetime:
    return datetime.now(UTC)


NowDep = Annotated[datetime, Depends(get_now)]


async def upsert_user(session: AsyncSession, tg: TelegramWebAppUser) -> User:
    values = {
        "telegram_id": tg.id,
        "first_name": tg.first_name,
        "last_name": tg.last_name,
        "username": tg.username,
        "language_code": tg.language_code,
    }
    stmt = (
        insert(User)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[User.telegram_id],
            set_={k: v for k, v in values.items() if k != "telegram_id"},
        )
        .returning(User.id)
    )
    user_id = (await session.execute(stmt)).scalar_one()
    await session.commit()
    user = await session.get(User, user_id, populate_existing=True)
    assert user is not None
    return user


async def get_current_user(
    session: SessionDep,
    now: NowDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.startswith("tma "):
        raise Unauthorized()
    try:
        data = validate_init_data(
            authorization[4:],
            settings.bot_token,
            max_age_seconds=settings.init_data_max_age_seconds,
            now=now,
        )
    except InitDataError as e:
        raise Unauthorized("Сессия устарела. Закройте и снова откройте приложение.") from e
    return await upsert_user(session, data.user)


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass
class StaffContext:
    staff: Staff
    salon: Salon
    user: User

    @property
    def is_admin(self) -> bool:
        return self.staff.role in ADMIN_ROLES

    def ensure_can_manage_staff(self, staff_id: int) -> None:
        """Мастер работает только со своими данными, админ — со всеми."""
        if not self.is_admin and staff_id != self.staff.id:
            raise Forbidden()


def require_staff(*roles: StaffRole) -> Callable[..., Awaitable[StaffContext]]:
    allowed = set(roles) if roles else set(StaffRole)

    async def dependency(salon_id: int, session: SessionDep, user: CurrentUser) -> StaffContext:
        staff = (
            await session.execute(
                select(Staff).where(
                    Staff.salon_id == salon_id,
                    Staff.user_id == user.id,
                    Staff.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if staff is None:
            raise Forbidden("Вы не сотрудник этого салона")
        if staff.role not in allowed:
            raise Forbidden()
        salon = await session.get(Salon, salon_id)
        if salon is None:
            raise NotFound("Салон не найден")
        return StaffContext(staff=staff, salon=salon, user=user)

    return dependency


StaffDep = Annotated[StaffContext, Depends(require_staff())]
AdminDep = Annotated[StaffContext, Depends(require_staff(*ADMIN_ROLES))]
