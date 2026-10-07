import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from aiogram.types import Update
from fastapi import APIRouter, FastAPI, Header, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.admin import admin_secret_key, setup_admin
from app.api import me, public
from app.api.manage import router as manage_router
from app.bot.setup import configure_telegram, create_bot, create_dispatcher
from app.config import settings
from app.db import SessionLocal, engine
from app.errors import install_error_handlers
from app.logging_setup import setup_logging, setup_sentry

log = logging.getLogger("app")

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    if settings.telegram_setup_on_startup:
        try:
            await configure_telegram(app.state.bot)
        except Exception:
            log.exception("telegram setup failed")
    yield
    await app.state.bot.session.close()
    await engine.dispose()


def create_app() -> FastAPI:
    setup_sentry()
    app = FastAPI(
        title="Salon booking",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.environment != "production" else None,
    )
    app.state.bot = create_bot()
    app.state.dp = create_dispatcher()

    install_error_handlers(app)

    @app.middleware("http")
    async def access_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/tg/webhook/"):
            path = "/tg/webhook/***"  # секрет в пути не логируем
        # query string не логируем: в поиске клиентов бывают телефоны
        log.info(
            "request",
            extra={
                "method": request.method,
                "path": path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return response

    api = APIRouter(prefix="/api")
    api.include_router(public.router)
    api.include_router(me.router)
    api.include_router(manage_router)
    app.include_router(api)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/privacy", include_in_schema=False, response_class=HTMLResponse)
    async def privacy() -> HTMLResponse:
        path = Path(settings.privacy_html_path) if settings.privacy_html_path else None
        if path is None or not path.is_file():
            path = STATIC_DIR / "privacy.html"
        return HTMLResponse(path.read_text(encoding="utf-8"))

    @app.post("/tg/webhook/{secret}", include_in_schema=False)
    async def telegram_webhook(
        secret: str,
        request: Request,
        x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        if (
            not settings.webhook_secret
            or secret != settings.webhook_secret
            or x_telegram_bot_api_secret_token != settings.webhook_secret
        ):
            return JSONResponse({"error": "forbidden", "message": "forbidden"}, status_code=403)
        update = Update.model_validate(await request.json(), context={"bot": app.state.bot})
        await app.state.dp.feed_update(app.state.bot, update)
        return JSONResponse({"ok": True})

    app.add_middleware(SessionMiddleware, secret_key=admin_secret_key(), https_only=False)
    setup_admin(app)
    return app


app = create_app()
