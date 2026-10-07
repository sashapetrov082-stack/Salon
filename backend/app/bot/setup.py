"""Создание Bot/Dispatcher и настройка webhook и menu button."""

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import MenuButtonWebApp, WebAppInfo

from app.bot.router import router
from app.config import settings
from app.db import SessionLocal

log = logging.getLogger(__name__)


def create_bot() -> Bot:
    return Bot(
        token=settings.bot_token or "0:missing",
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(sessionmaker=SessionLocal)
    dp.include_router(router)
    return dp


async def configure_telegram(bot: Bot) -> None:
    """Регистрирует webhook и кнопку меню, открывающую Mini App."""
    if not (settings.bot_token and settings.webhook_base_url and settings.webhook_secret):
        log.warning("telegram setup skipped: BOT_TOKEN/WEBHOOK_* not configured")
        return
    url = settings.webhook_base_url.rstrip("/") + settings.webhook_path
    await bot.set_webhook(
        url=url,
        secret_token=settings.webhook_secret,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=False,
    )
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Открыть", web_app=WebAppInfo(url=settings.miniapp_url))
    )
    log.info("telegram webhook configured")
