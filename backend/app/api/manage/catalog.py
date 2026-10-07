"""Категории и услуги (администратор). Чтение доступно и мастеру."""

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import AdminDep, SessionDep, StaffContext, StaffDep
from app.errors import AppError, NotFound
from app.models import Appointment, Service, ServiceCategory
from app.schemas.common import Ok
from app.schemas.manage import CategoryIn, CategoryOut, ServiceAdminOut, ServiceIn

router = APIRouter()


async def _category(session: SessionDep, ctx: StaffContext, category_id: int) -> ServiceCategory:
    cat = await session.get(ServiceCategory, category_id)
    if cat is None or cat.salon_id != ctx.salon.id:
        raise NotFound("Категория не найдена")
    return cat


async def _service(session: SessionDep, ctx: StaffContext, service_id: int) -> Service:
    service = await session.get(Service, service_id)
    if service is None or service.salon_id != ctx.salon.id:
        raise NotFound("Услуга не найдена")
    return service


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(session: SessionDep, ctx: StaffDep) -> list[CategoryOut]:
    rows = (
        await session.execute(
            select(ServiceCategory)
            .where(ServiceCategory.salon_id == ctx.salon.id)
            .order_by(ServiceCategory.sort_order, ServiceCategory.id)
        )
    ).scalars()
    return [CategoryOut.model_validate(c) for c in rows]


@router.post("/categories", response_model=CategoryOut, status_code=201)
async def create_category(body: CategoryIn, session: SessionDep, ctx: AdminDep) -> CategoryOut:
    cat = ServiceCategory(salon_id=ctx.salon.id, **body.model_dump())
    session.add(cat)
    await session.commit()
    return CategoryOut.model_validate(cat)


@router.put("/categories/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: int, body: CategoryIn, session: SessionDep, ctx: AdminDep
) -> CategoryOut:
    cat = await _category(session, ctx, category_id)
    for k, v in body.model_dump().items():
        setattr(cat, k, v)
    await session.commit()
    return CategoryOut.model_validate(cat)


@router.delete("/categories/{category_id}", response_model=Ok)
async def delete_category(category_id: int, session: SessionDep, ctx: AdminDep) -> Ok:
    cat = await _category(session, ctx, category_id)
    count = (
        await session.execute(
            select(func.count()).select_from(Service).where(Service.category_id == cat.id)
        )
    ).scalar_one()
    if count:
        raise AppError("category_not_empty", "Сначала перенесите или удалите услуги категории")
    await session.delete(cat)
    await session.commit()
    return Ok()


@router.get("/services", response_model=list[ServiceAdminOut])
async def list_services(session: SessionDep, ctx: StaffDep) -> list[ServiceAdminOut]:
    rows = (
        await session.execute(
            select(Service)
            .where(Service.salon_id == ctx.salon.id)
            .order_by(Service.sort_order, Service.id)
        )
    ).scalars()
    return [ServiceAdminOut.model_validate(s) for s in rows]


@router.post("/services", response_model=ServiceAdminOut, status_code=201)
async def create_service(body: ServiceIn, session: SessionDep, ctx: AdminDep) -> ServiceAdminOut:
    await _category(session, ctx, body.category_id)
    service = Service(salon_id=ctx.salon.id, **body.model_dump())
    session.add(service)
    await session.commit()
    return ServiceAdminOut.model_validate(service)


@router.put("/services/{service_id}", response_model=ServiceAdminOut)
async def update_service(
    service_id: int, body: ServiceIn, session: SessionDep, ctx: AdminDep
) -> ServiceAdminOut:
    service = await _service(session, ctx, service_id)
    await _category(session, ctx, body.category_id)
    for k, v in body.model_dump().items():
        setattr(service, k, v)
    await session.commit()
    return ServiceAdminOut.model_validate(service)


@router.delete("/services/{service_id}", response_model=Ok)
async def delete_service(service_id: int, session: SessionDep, ctx: AdminDep) -> Ok:
    """Услуги с историей записей не удаляются, а выключаются."""
    service = await _service(session, ctx, service_id)
    used = (
        await session.execute(
            select(func.count())
            .select_from(Appointment)
            .where(Appointment.service_id == service.id)
        )
    ).scalar_one()
    if used:
        service.is_active = False
    else:
        await session.delete(service)
    await session.commit()
    return Ok()
