from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Ошибка бизнес-логики с кодом и текстом для пользователя."""

    status_code = 400

    def __init__(self, code: str, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class NotFound(AppError):
    status_code = 404

    def __init__(self, message: str = "Не найдено") -> None:
        super().__init__("not_found", message)


class Forbidden(AppError):
    status_code = 403

    def __init__(self, message: str = "Недостаточно прав") -> None:
        super().__init__("forbidden", message)


class Unauthorized(AppError):
    status_code = 401

    def __init__(self, message: str = "Откройте приложение из Telegram") -> None:
        super().__init__("unauthorized", message)


class SlotTaken(AppError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("slot_taken", "Это время уже заняли. Выберите другое.")


def _json(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "message": message})


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return _json(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        resp = _json(422, "validation_error", "Проверьте введённые данные")
        return resp

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed", 401: "unauthorized"}
        message = exc.detail if isinstance(exc.detail, str) else "Ошибка запроса"
        return _json(exc.status_code, codes.get(exc.status_code, "http_error"), message)
