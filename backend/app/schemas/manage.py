from datetime import date, datetime, time
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.models import AppointmentStatus, StaffRole
from app.schemas.common import (
    Aware,
    BufferMinutes,
    LongText,
    Minutes,
    Name,
    Out,
    Price,
    SortOrder,
    TimezoneName,
    Url,
    Weekday,
    time_range_ok,
)


class ClientBrief(Out):
    id: int
    name: str
    phone: str
    visits_count: int
    no_show_count: int


class ServiceRef(Out):
    id: int
    name: str


class ManageAppointmentOut(Out):
    id: int
    status: AppointmentStatus
    source: str
    staff_id: int
    starts_at: datetime
    ends_at: datetime
    blocked_until: datetime
    price: int
    price_is_from: bool
    comment: str | None
    service: ServiceRef
    client: ClientBrief


class TimeOffIn(BaseModel):
    starts_at: Aware
    ends_at: Aware
    reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _range(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class TimeOffOut(Out):
    id: int
    staff_id: int
    starts_at: datetime
    ends_at: datetime
    reason: str | None


class StaffCalendarOut(Out):
    id: int
    display_name: str
    photo_url: str | None
    is_bookable: bool
    sort_order: int


class CalendarOut(BaseModel):
    appointments: list[ManageAppointmentOut]
    time_off: list[TimeOffOut]
    staff: list[StaffCalendarOut]


class NewClientIn(BaseModel):
    name: Name
    phone: str = Field(min_length=5, max_length=32)


class ManualAppointmentIn(BaseModel):
    staff_id: int
    service_id: int
    starts_at: Aware
    client_id: int | None = None
    client: NewClientIn | None = None
    comment: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _client(self) -> Self:
        if (self.client_id is None) == (self.client is None):
            raise ValueError("either client_id or client is required")
        return self


class AppointmentPatch(BaseModel):
    status: AppointmentStatus | None = None
    starts_at: Aware | None = None
    staff_id: int | None = None


class WeeklyIn(BaseModel):
    weekday: Weekday
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def _range(self) -> Self:
        if not time_range_ok(self.start_time, self.end_time):
            raise ValueError("end_time must be after start_time")
        return self


class WeeklyOut(Out):
    weekday: int
    start_time: time
    end_time: time


class ScheduleIn(BaseModel):
    work: list[WeeklyIn] = Field(max_length=50)
    breaks: list[WeeklyIn] = Field(default=[], max_length=50)


class ScheduleOut(BaseModel):
    work: list[WeeklyOut]
    breaks: list[WeeklyOut]


class OverrideIn(BaseModel):
    date: date
    is_day_off: bool = False
    start_time: time | None = None
    end_time: time | None = None

    @model_validator(mode="after")
    def _range(self) -> Self:
        if self.is_day_off:
            self.start_time = self.end_time = None
            return self
        if self.start_time is None or self.end_time is None:
            raise ValueError("start_time and end_time are required")
        if not time_range_ok(self.start_time, self.end_time):
            raise ValueError("end_time must be after start_time")
        return self


class OverrideOut(Out):
    id: int
    staff_id: int
    date: date
    is_day_off: bool
    start_time: time | None
    end_time: time | None


class CategoryIn(BaseModel):
    name: Name
    sort_order: SortOrder = 0


class CategoryOut(Out):
    id: int
    name: str
    sort_order: int


class ServiceIn(BaseModel):
    category_id: int
    name: Name
    description: LongText | None = None
    price: Price
    price_is_from: bool = False
    duration_min: Minutes
    buffer_after_min: BufferMinutes = 0
    is_active: bool = True
    sort_order: SortOrder = 0


class ServiceAdminOut(Out):
    id: int
    category_id: int
    name: str
    description: str | None
    price: int
    price_is_from: bool
    duration_min: int
    buffer_after_min: int
    is_active: bool
    sort_order: int


class StaffIn(BaseModel):
    display_name: Name
    role: StaffRole = StaffRole.master
    photo_url: Url | None = None
    description: LongText | None = None
    is_bookable: bool = True
    is_active: bool = True
    sort_order: SortOrder = 0


class StaffServiceIn(BaseModel):
    service_id: int
    price_override: Price | None = None
    duration_override_min: Minutes | None = None


class StaffServiceOut(Out):
    service_id: int
    price_override: int | None
    duration_override_min: int | None


class StaffAdminOut(Out):
    id: int
    display_name: str
    role: StaffRole
    photo_url: str | None
    description: str | None
    is_bookable: bool
    is_active: bool
    sort_order: int
    is_linked: bool
    telegram_username: str | None = None
    services: list[StaffServiceOut] = []


class InviteOut(BaseModel):
    token: str
    url: str
    expires_at: datetime


class ClientOut(Out):
    id: int
    name: str
    phone: str
    notes: str | None
    visits_count: int
    no_show_count: int
    has_telegram: bool = False


class ClientHistoryItem(Out):
    id: int
    status: AppointmentStatus
    starts_at: datetime
    price: int
    price_is_from: bool
    service: ServiceRef
    staff_name: str


class ClientDetailOut(ClientOut):
    appointments: list[ClientHistoryItem]


class ClientPatch(BaseModel):
    name: Name | None = None
    phone: str | None = Field(default=None, min_length=5, max_length=32)
    notes: str | None = Field(default=None, max_length=2000)


class SettingsOut(Out):
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
    booking_link: str = ""
    photos: list["PhotoAdminOut"] = []


class SettingsPatch(BaseModel):
    name: Name | None = None
    description: LongText | None = None
    address: str | None = Field(default=None, max_length=300)
    map_url: Url | None = None
    phone: str | None = Field(default=None, max_length=32)
    cover_url: Url | None = None
    logo_url: Url | None = None
    announcement: str | None = Field(default=None, max_length=500)
    timezone: TimezoneName | None = None
    slot_step_min: int | None = Field(default=None, ge=5, le=120)
    min_lead_time_min: int | None = Field(default=None, ge=0, le=7 * 24 * 60)
    booking_horizon_days: int | None = Field(default=None, ge=1, le=365)
    cancel_deadline_hours: int | None = Field(default=None, ge=0, le=7 * 24)


class PhotoIn(BaseModel):
    url: Url
    sort_order: SortOrder = 0


class PhotoAdminOut(Out):
    id: int
    url: str
    sort_order: int


class UploadOut(BaseModel):
    url: str
