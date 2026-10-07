"""База клиентов салона."""

from fastapi import APIRouter
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import SessionDep, StaffContext, StaffDep
from app.errors import AppError, NotFound
from app.models import Appointment, Client
from app.schemas.manage import (
    ClientDetailOut,
    ClientHistoryItem,
    ClientOut,
    ClientPatch,
    ServiceRef,
)
from app.services.formatting import normalize_phone

router = APIRouter(prefix="/clients")


def _out(client: Client) -> ClientOut:
    out = ClientOut.model_validate(client)
    out.has_telegram = client.user_id is not None
    return out


async def _get(session: SessionDep, ctx: StaffContext, client_id: int) -> Client:
    client = await session.get(Client, client_id)
    if client is None or client.salon_id != ctx.salon.id:
        raise NotFound("Клиент не найден")
    return client


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("", response_model=list[ClientOut])
async def search_clients(
    session: SessionDep, ctx: StaffDep, q: str = "", limit: int = 50
) -> list[ClientOut]:
    stmt = select(Client).where(Client.salon_id == ctx.salon.id)
    q = q.strip()
    if q:
        conds = [Client.name.ilike(f"%{_escape_like(q)}%", escape="\\")]
        digits = "".join(ch for ch in q if ch.isdigit())
        if len(digits) >= 3:
            if len(digits) == 11 and digits[0] == "8":
                digits = "7" + digits[1:]
            conds.append(Client.phone.like(f"%{digits}%"))
        stmt = stmt.where(or_(*conds))
    rows = (
        await session.execute(stmt.order_by(Client.name, Client.id).limit(min(limit, 200)))
    ).scalars()
    return [_out(c) for c in rows]


async def _detail(session: SessionDep, client: Client) -> ClientDetailOut:
    appts = (
        await session.execute(
            select(Appointment)
            .where(Appointment.client_id == client.id)
            .options(selectinload(Appointment.service), selectinload(Appointment.staff))
            .order_by(Appointment.starts_at.desc())
            .limit(100)
        )
    ).scalars()
    base = _out(client)
    return ClientDetailOut(
        **base.model_dump(),
        appointments=[
            ClientHistoryItem(
                id=a.id,
                status=a.status,
                starts_at=a.starts_at,
                price=a.price,
                price_is_from=a.price_is_from,
                service=ServiceRef(id=a.service.id, name=a.service.name),
                staff_name=a.staff.display_name,
            )
            for a in appts
        ],
    )


@router.get("/{client_id}", response_model=ClientDetailOut)
async def get_client(client_id: int, session: SessionDep, ctx: StaffDep) -> ClientDetailOut:
    return await _detail(session, await _get(session, ctx, client_id))


@router.patch("/{client_id}", response_model=ClientDetailOut)
async def patch_client(
    client_id: int, body: ClientPatch, session: SessionDep, ctx: StaffDep
) -> ClientDetailOut:
    client = await _get(session, ctx, client_id)
    data = body.model_dump(exclude_unset=True)
    if "phone" in data and data["phone"] is not None:
        phone = normalize_phone(data["phone"])
        if phone is None:
            raise AppError("invalid_phone", "Проверьте номер телефона")
        data["phone"] = phone
    for k, v in data.items():
        if k == "notes":
            client.notes = (v or "").strip() or None
        elif v is not None:
            setattr(client, k, v)
    await session.commit()
    return await _detail(session, client)
