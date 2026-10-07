from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, IdMixin, TimestampMixin
from app.models._types import pg_enum
from app.models.client import Client
from app.models.enums import AppointmentSource, AppointmentStatus
from app.models.salon import Salon
from app.models.service import Service
from app.models.staff import Staff


class Appointment(IdMixin, TimestampMixin, Base):
    __tablename__ = "appointment"

    salon_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("salon.id", ondelete="CASCADE"))
    staff_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("staff.id", ondelete="RESTRICT"))
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("client.id", ondelete="RESTRICT"), index=True
    )
    service_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("service.id", ondelete="RESTRICT")
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    blocked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[AppointmentStatus] = mapped_column(
        pg_enum(AppointmentStatus, "appointment_status"),
        server_default=AppointmentStatus.booked.value,
        default=AppointmentStatus.booked,
    )
    source: Mapped[AppointmentSource] = mapped_column(
        pg_enum(AppointmentSource, "appointment_source")
    )
    price: Mapped[int] = mapped_column(Integer)
    price_is_from: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    comment: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="SET NULL")
    )

    salon: Mapped[Salon] = relationship()
    staff: Mapped[Staff] = relationship()
    client: Mapped[Client] = relationship()
    service: Mapped[Service] = relationship()

    @property
    def is_active(self) -> bool:
        return self.status in (AppointmentStatus.booked, AppointmentStatus.confirmed)

    def __str__(self) -> str:
        return f"#{self.id} {self.starts_at:%Y-%m-%d %H:%M}"


Index("ix_appointment_salon_starts", Appointment.salon_id, Appointment.starts_at)
Index("ix_appointment_staff_starts", Appointment.staff_id, Appointment.starts_at)

# Защита от двойной записи (нужно расширение btree_gist).
Appointment.__table__.append_constraint(  # type: ignore[attr-defined]
    ExcludeConstraint(
        (Appointment.staff_id, "="),
        (func.tstzrange(Appointment.starts_at, Appointment.blocked_until, "[)"), "&&"),
        name="appointment_no_overlap",
        using="gist",
        where=text("status IN ('booked', 'confirmed')"),
    )
)
