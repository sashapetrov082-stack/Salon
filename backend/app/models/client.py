from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, IdMixin, TimestampMixin


class Client(IdMixin, TimestampMixin, Base):
    """Клиент в контексте конкретного салона."""

    __tablename__ = "client"
    __table_args__ = (
        Index(
            "uq_client_salon_user",
            "salon_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index("ix_client_salon_phone", "salon_id", "phone"),
    )

    salon_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("salon.id", ondelete="CASCADE"))
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    visits_count: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0)
    no_show_count: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0)

    def __str__(self) -> str:
        return self.name
