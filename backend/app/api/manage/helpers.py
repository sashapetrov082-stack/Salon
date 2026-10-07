from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import StaffContext
from app.errors import NotFound
from app.models import Staff


async def get_salon_staff(session: AsyncSession, ctx: StaffContext, staff_id: int) -> Staff:
    """Сотрудник этого салона; мастер может обращаться только к себе."""
    ctx.ensure_can_manage_staff(staff_id)
    staff = await session.get(Staff, staff_id)
    if staff is None or staff.salon_id != ctx.salon.id:
        raise NotFound("Сотрудник не найден")
    return staff
