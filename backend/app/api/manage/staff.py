"""Сотрудники салона, привязка услуг, приглашения."""

from fastapi import APIRouter
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminDep, NowDep, SessionDep, StaffContext, StaffDep
from app.config import settings
from app.errors import AppError, Forbidden, NotFound
from app.models import Appointment, Service, Staff, StaffRole, StaffService
from app.schemas.common import Ok
from app.schemas.manage import (
    InviteOut,
    StaffAdminOut,
    StaffIn,
    StaffServiceIn,
    StaffServiceOut,
)
from app.services import invites

router = APIRouter(prefix="/staff")


async def _services(session: SessionDep, staff_id: int) -> list[StaffServiceOut]:
    rows = (
        await session.execute(select(StaffService).where(StaffService.staff_id == staff_id))
    ).scalars()
    return [StaffServiceOut.model_validate(r) for r in rows]


async def _out(session: SessionDep, staff: Staff) -> StaffAdminOut:
    out = StaffAdminOut(
        id=staff.id,
        display_name=staff.display_name,
        role=staff.role,
        photo_url=staff.photo_url,
        description=staff.description,
        is_bookable=staff.is_bookable,
        is_active=staff.is_active,
        sort_order=staff.sort_order,
        is_linked=staff.user_id is not None,
        telegram_username=staff.user.username if staff.user else None,
    )
    out.services = await _services(session, staff.id)
    return out


async def _get(session: SessionDep, ctx: StaffContext, staff_id: int) -> Staff:
    staff = await session.get(
        Staff, staff_id, options=[selectinload(Staff.user)], populate_existing=True
    )
    if staff is None or staff.salon_id != ctx.salon.id:
        raise NotFound("Сотрудник не найден")
    return staff


def _check_owner_rules(ctx: StaffContext, staff: Staff | None, new_role: StaffRole) -> None:
    if ctx.staff.role == StaffRole.owner:
        return
    if new_role == StaffRole.owner or (staff is not None and staff.role == StaffRole.owner):
        raise Forbidden("Только владелец может управлять ролью «владелец»")


@router.get("", response_model=list[StaffAdminOut])
async def list_staff(session: SessionDep, ctx: StaffDep) -> list[StaffAdminOut]:
    rows = (
        (
            await session.execute(
                select(Staff)
                .where(Staff.salon_id == ctx.salon.id)
                .options(selectinload(Staff.user))
                .order_by(Staff.sort_order, Staff.id)
            )
        )
        .scalars()
        .all()
    )
    return [await _out(session, s) for s in rows]


@router.post("", response_model=StaffAdminOut, status_code=201)
async def create_staff(body: StaffIn, session: SessionDep, ctx: AdminDep) -> StaffAdminOut:
    _check_owner_rules(ctx, None, body.role)
    staff = Staff(salon_id=ctx.salon.id, **body.model_dump())
    session.add(staff)
    await session.commit()
    return await _out(session, await _get(session, ctx, staff.id))


@router.get("/{staff_id}", response_model=StaffAdminOut)
async def get_staff(staff_id: int, session: SessionDep, ctx: StaffDep) -> StaffAdminOut:
    return await _out(session, await _get(session, ctx, staff_id))


@router.put("/{staff_id}", response_model=StaffAdminOut)
async def update_staff(
    staff_id: int, body: StaffIn, session: SessionDep, ctx: AdminDep
) -> StaffAdminOut:
    staff = await _get(session, ctx, staff_id)
    _check_owner_rules(ctx, staff, body.role)
    if staff.id == ctx.staff.id and (not body.is_active or body.role != staff.role):
        raise AppError("self_edit", "Нельзя отключить себя или изменить свою роль")
    for k, v in body.model_dump().items():
        setattr(staff, k, v)
    await session.commit()
    return await _out(session, await _get(session, ctx, staff_id))


@router.delete("/{staff_id}", response_model=Ok)
async def delete_staff(staff_id: int, session: SessionDep, ctx: AdminDep) -> Ok:
    """Сотрудник с историей записей не удаляется, а отключается."""
    staff = await _get(session, ctx, staff_id)
    _check_owner_rules(ctx, staff, staff.role)
    if staff.id == ctx.staff.id:
        raise AppError("self_edit", "Нельзя удалить себя")
    used = (
        await session.execute(
            select(func.count()).select_from(Appointment).where(Appointment.staff_id == staff.id)
        )
    ).scalar_one()
    if used:
        staff.is_active = False
    else:
        await session.delete(staff)
    await session.commit()
    return Ok()


@router.get("/{staff_id}/services", response_model=list[StaffServiceOut])
async def get_staff_services(
    staff_id: int, session: SessionDep, ctx: StaffDep
) -> list[StaffServiceOut]:
    await _get(session, ctx, staff_id)
    return await _services(session, staff_id)


@router.put("/{staff_id}/services", response_model=list[StaffServiceOut])
async def put_staff_services(
    staff_id: int, body: list[StaffServiceIn], session: SessionDep, ctx: AdminDep
) -> list[StaffServiceOut]:
    await _get(session, ctx, staff_id)
    ids = {item.service_id for item in body}
    if len(ids) != len(body):
        raise AppError("duplicate_service", "Услуга указана дважды")
    if ids:
        valid = set(
            (
                await session.execute(
                    select(Service.id).where(Service.salon_id == ctx.salon.id, Service.id.in_(ids))
                )
            ).scalars()
        )
        if valid != ids:
            raise NotFound("Услуга не найдена")
    await session.execute(delete(StaffService).where(StaffService.staff_id == staff_id))
    for item in body:
        session.add(StaffService(staff_id=staff_id, **item.model_dump()))
    await session.commit()
    return await _services(session, staff_id)


@router.post("/{staff_id}/invite", response_model=InviteOut, status_code=201)
async def create_invite(
    staff_id: int, session: SessionDep, ctx: AdminDep, now: NowDep
) -> InviteOut:
    staff = await _get(session, ctx, staff_id)
    _check_owner_rules(ctx, staff, staff.role)
    invite = await invites.create_invite(session, staff, now)
    await session.commit()
    return InviteOut(
        token=invite.token, url=settings.invite_link(invite.token), expires_at=invite.expires_at
    )
