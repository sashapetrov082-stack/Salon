from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, IdMixin, TimestampMixin
from app.models._types import pg_enum
from app.models.appointment import Appointment
from app.models.enums import NotificationKind, NotificationStatus
from app.models.user import User


class Notification(IdMixin, TimestampMixin, Base):
    __tablename__ = "notification"
    __table_args__ = (Index("ix_notification_status_send_at", "status", "send_at"),)

    appointment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("appointment.id", ondelete="CASCADE"), index=True
    )
    recipient_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE")
    )
    kind: Mapped[NotificationKind] = mapped_column(pg_enum(NotificationKind, "notification_kind"))
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[NotificationStatus] = mapped_column(
        pg_enum(NotificationStatus, "notification_status"),
        server_default=NotificationStatus.pending.value,
        default=NotificationStatus.pending,
    )
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0)
    last_error: Mapped[str | None] = mapped_column(Text)

    appointment: Mapped[Appointment] = relationship()
    recipient: Mapped[User] = relationship()
