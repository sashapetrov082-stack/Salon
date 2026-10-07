from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, IdMixin, TimestampMixin


class ServiceCategory(IdMixin, TimestampMixin, Base):
    __tablename__ = "service_category"

    salon_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("salon.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))

    def __str__(self) -> str:
        return self.name


class Service(IdMixin, TimestampMixin, Base):
    __tablename__ = "service"

    salon_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("salon.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("service_category.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[int] = mapped_column(Integer)
    price_is_from: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    duration_min: Mapped[int] = mapped_column(Integer)
    buffer_after_min: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))

    category: Mapped[ServiceCategory] = relationship()

    def __str__(self) -> str:
        return self.name


class StaffService(TimestampMixin, Base):
    __tablename__ = "staff_service"

    staff_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("staff.id", ondelete="CASCADE"), primary_key=True
    )
    service_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("service.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    price_override: Mapped[int | None] = mapped_column(Integer)
    duration_override_min: Mapped[int | None] = mapped_column(Integer)
