from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, IdMixin, TimestampMixin


class Salon(IdMixin, TimestampMixin, Base):
    __tablename__ = "salon"

    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    map_url: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    cover_url: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(Text)
    announcement: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, server_default=text("'Europe/Moscow'"))
    slot_step_min: Mapped[int] = mapped_column(Integer, server_default=text("15"))
    min_lead_time_min: Mapped[int] = mapped_column(Integer, server_default=text("60"))
    booking_horizon_days: Mapped[int] = mapped_column(Integer, server_default=text("30"))
    cancel_deadline_hours: Mapped[int] = mapped_column(Integer, server_default=text("3"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    photos: Mapped[list["SalonPhoto"]] = relationship(
        back_populates="salon", order_by="SalonPhoto.sort_order", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"


class SalonPhoto(IdMixin, TimestampMixin, Base):
    __tablename__ = "salon_photo"

    salon_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("salon.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))

    salon: Mapped[Salon] = relationship(back_populates="photos")
