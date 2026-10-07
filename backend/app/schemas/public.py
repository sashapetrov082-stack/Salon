from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import Aware, Out, ServiceBrief, StaffBrief


class PhotoOut(Out):
    id: int
    url: str
    sort_order: int


class ClientProfile(BaseModel):
    name: str
    phone: str


class SalonPublicOut(Out):
    id: int
    slug: str
    name: str
    description: str | None
    address: str | None
    map_url: str | None
    phone: str | None
    cover_url: str | None
    logo_url: str | None
    announcement: str | None
    timezone: str
    slot_step_min: int
    min_lead_time_min: int
    booking_horizon_days: int
    cancel_deadline_hours: int
    is_active: bool
    photos: list[PhotoOut] = []
    client: ClientProfile | None = None


class ServiceOut(Out):
    id: int
    category_id: int
    name: str
    description: str | None
    price: int
    price_is_from: bool
    duration_min: int


class CategoryWithServices(Out):
    id: int
    name: str
    services: list[ServiceOut]


class StaffPublicOut(Out):
    id: int
    display_name: str
    photo_url: str | None
    description: str | None
    nearest_slot: datetime | None = None
    price: int | None = None
    price_is_from: bool = False
    duration_min: int | None = None


class DayAvailability(BaseModel):
    date: date
    has_slots: bool


class SlotOut(BaseModel):
    starts_at: datetime
    staff_id: int


class AppointmentCreate(BaseModel):
    service_id: int
    staff_id: int | None = None
    starts_at: Aware
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    comment: str | None = Field(default=None, max_length=500)


class SalonBrief(Out):
    id: int
    slug: str
    name: str
    address: str | None
    phone: str | None
    map_url: str | None
    timezone: str
    cancel_deadline_hours: int
    logo_url: str | None = None


class ClientAppointmentOut(Out):
    id: int
    status: str
    starts_at: datetime
    ends_at: datetime
    price: int
    price_is_from: bool
    comment: str | None
    salon: SalonBrief
    service: ServiceBrief
    staff: StaffBrief
    can_change: bool = False
