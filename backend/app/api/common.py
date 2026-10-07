from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Appointment
from app.schemas.common import ServiceBrief, StaffBrief
from app.schemas.public import ClientAppointmentOut, SalonBrief
from app.services.booking import can_client_change

APPOINTMENT_OPTIONS = (
    selectinload(Appointment.salon),
    selectinload(Appointment.service),
    selectinload(Appointment.staff),
    selectinload(Appointment.client),
)


async def load_client_appointment(session: AsyncSession, appointment_id: int) -> Appointment:
    appt = await session.get(
        Appointment, appointment_id, options=APPOINTMENT_OPTIONS, populate_existing=True
    )
    assert appt is not None
    return appt


def client_appointment_out(appt: Appointment, now: datetime) -> ClientAppointmentOut:
    return ClientAppointmentOut(
        id=appt.id,
        status=appt.status.value,
        starts_at=appt.starts_at,
        ends_at=appt.ends_at,
        price=appt.price,
        price_is_from=appt.price_is_from,
        comment=appt.comment,
        salon=SalonBrief.model_validate(appt.salon),
        service=ServiceBrief(
            id=appt.service.id,
            name=appt.service.name,
            duration_min=int((appt.ends_at - appt.starts_at).total_seconds() // 60),
        ),
        staff=StaffBrief.model_validate(appt.staff),
        can_change=can_client_change(appt, appt.salon, now),
    )
