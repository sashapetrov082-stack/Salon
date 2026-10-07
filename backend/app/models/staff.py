from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, IdMixin, TimestampMixin
from app.models._types import pg_enum
from app.models.enums import ADMIN_ROLES, StaffRole
from app.models.salon import Salon
from app.models.user import User


class Staff(IdMixin, TimestampMixin, Base):
    __tablename__ = "staff"
    __table_args__ = (UniqueConstraint("salon_id", "user_id"),)

    salon_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("salon.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    role: Mapped[StaffRole] = mapped_column(pg_enum(StaffRole, "staff_role"))
    display_name: Mapped[str] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    is_bookable: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))

    salon: Mapped[Salon] = relationship()
    user: Mapped[User | None] = relationship()

    @property
    def is_admin(self) -> bool:
        return self.role in ADMIN_ROLES

    def __str__(self) -> str:
        return f"{self.display_name} ({self.role})"


class StaffInvite(IdMixin, TimestampMixin, Base):
    __tablename__ = "staff_invite"

    salon_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("salon.id", ondelete="CASCADE"), index=True
    )
    staff_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("staff.id", ondelete="CASCADE"), index=True
    )
    token: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    salon: Mapped[Salon] = relationship()
    staff: Mapped[Staff] = relationship()
