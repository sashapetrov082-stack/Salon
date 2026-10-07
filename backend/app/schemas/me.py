from pydantic import BaseModel

from app.schemas.common import Aware, Out


class StaffSalon(BaseModel):
    salon_id: int
    salon_name: str
    salon_slug: str
    staff_id: int
    role: str


class VisitedSalon(Out):
    id: int
    slug: str
    name: str
    logo_url: str | None
    address: str | None


class MeOut(BaseModel):
    id: int
    telegram_id: int
    first_name: str | None
    last_name: str | None
    username: str | None
    is_staff: bool
    staff_salons: list[StaffSalon]
    visited_salons: list[VisitedSalon]


class ContactStatus(BaseModel):
    received: bool
    phone: str | None = None


class RescheduleIn(BaseModel):
    starts_at: Aware
    staff_id: int | None = None
