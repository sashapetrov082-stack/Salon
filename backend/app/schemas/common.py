from datetime import datetime, time
from typing import Annotated
from zoneinfo import available_timezones

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


Name = Annotated[str, Field(min_length=1, max_length=120)]
LongText = Annotated[str, Field(max_length=2000)]


def _check_url(v: str) -> str:
    if not (v.startswith("https://") or v.startswith("http://")):
        raise ValueError("url must start with http(s)://")
    return v


Url = Annotated[str, Field(max_length=1000), AfterValidator(_check_url)]
Price = Annotated[int, Field(ge=0, le=10_000_000)]
Minutes = Annotated[int, Field(ge=5, le=24 * 60)]
BufferMinutes = Annotated[int, Field(ge=0, le=24 * 60)]
SortOrder = Annotated[int, Field(ge=-100_000, le=100_000)]
Weekday = Annotated[int, Field(ge=0, le=6)]
Aware = AwareDatetime


def _check_tz(v: str) -> str:
    if v not in available_timezones():
        raise ValueError("unknown timezone")
    return v


TimezoneName = Annotated[str, AfterValidator(_check_tz)]


def time_range_ok(start: time, end: time) -> bool:
    """end == 00:00 означает конец суток."""
    return end == time(0, 0) or start < end


class StaffBrief(Out):
    id: int
    display_name: str
    photo_url: str | None = None


class ServiceBrief(Out):
    id: int
    name: str
    duration_min: int


class Ok(BaseModel):
    ok: bool = True


class TimeRangeOut(Out):
    starts_at: datetime
    ends_at: datetime
