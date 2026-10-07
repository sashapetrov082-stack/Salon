from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, Message


class MockSession(BaseSession):
    """Сессия aiogram, которая ничего не отправляет, а запоминает вызовы."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self.fail_with: Exception | None = None

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109
    ) -> Any:
        if self.fail_with is not None:
            raise self.fail_with
        self.calls.append(method)
        if method.__returning__ is bool:
            return True
        return Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=Chat(id=getattr(method, "chat_id", 1) or 1, type="private"),
            text=getattr(method, "text", None),
        )

    def stream_content(  # pragma: no cover
        self, *args: Any, **kwargs: Any
    ) -> Any:
        raise NotImplementedError

    async def close(self) -> None:
        pass

    def of(self, name: str) -> list[Any]:
        return [c for c in self.calls if type(c).__name__ == name]
