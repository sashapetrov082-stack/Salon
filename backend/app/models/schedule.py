from datetime import date, datetime, time

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, SmallInteger, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, IdMixin, TimestampMixin


class WorkSchedule(IdMixin, TimestampMixin, Base):
    """Еженедельный шаблон смен. weekday: 0=пн..6=вс."""

    __tablename__ = "work_schedule"

    staff_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("staff.id", ondelete="CASCADE"), index=True
    )
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)


class ScheduleBreak(IdMixin, TimestampMixin, Base):
    """Регулярный перерыв (обед) по дню недели."""

    __tablename__ = "schedule_break"

    staff_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("staff.id", ondelete="CASCADE"), index=True
    )
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)


class ScheduleOverride(IdMixin, TimestampMixin, Base):
    """Исключение на дату: целиком заменяет недельный шаблон на эту дату."""

    __tablename__ = "schedule_override"

    staff_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("staff.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    is_day_off: Mapped[bool] = mapped_column(Boolean, default=False)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)


class TimeOff(IdMixin, TimestampMixin, Base):
    """Разовые блокировки: перерыв, отпуск, ручная блокировка времени."""

    __tablename__ = "time_off"

    staff_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("staff.id", ondelete="CASCADE"), index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)
