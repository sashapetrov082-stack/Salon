"""Настройки салона, галерея, загрузка изображений."""

import io
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.api.deps import AdminDep, SessionDep, StaffContext, StaffDep
from app.config import settings
from app.errors import AppError, NotFound
from app.models import Salon, SalonPhoto
from app.schemas.common import Ok
from app.schemas.manage import (
    PhotoAdminOut,
    PhotoIn,
    SettingsOut,
    SettingsPatch,
    UploadOut,
)

router = APIRouter()

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_SIDE = 1600
FORMATS = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}


async def _settings(session: SessionDep, ctx: StaffContext) -> SettingsOut:
    salon = (
        await session.execute(
            select(Salon)
            .where(Salon.id == ctx.salon.id)
            .options(selectinload(Salon.photos))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    out = SettingsOut.model_validate(salon)
    out.booking_link = settings.salon_link(salon.slug)
    out.photos = [PhotoAdminOut.model_validate(p) for p in salon.photos]
    return out


@router.get("/settings", response_model=SettingsOut)
async def get_settings(session: SessionDep, ctx: StaffDep) -> SettingsOut:
    return await _settings(session, ctx)


@router.patch("/settings", response_model=SettingsOut)
async def patch_settings(body: SettingsPatch, session: SessionDep, ctx: AdminDep) -> SettingsOut:
    data = body.model_dump(exclude_unset=True)
    required = {
        "name",
        "timezone",
        "slot_step_min",
        "min_lead_time_min",
        "booking_horizon_days",
        "cancel_deadline_hours",
    }
    for k, v in data.items():
        if v is None and k in required:
            raise AppError("validation_error", "Поле обязательно")
        if isinstance(v, str):
            v = v.strip() or None
            if v is None and k in required:
                raise AppError("validation_error", "Поле обязательно")
        setattr(ctx.salon, k, v)
    await session.commit()
    return await _settings(session, ctx)


@router.post("/photos", response_model=PhotoAdminOut, status_code=201)
async def add_photo(body: PhotoIn, session: SessionDep, ctx: AdminDep) -> PhotoAdminOut:
    photo = SalonPhoto(salon_id=ctx.salon.id, url=body.url, sort_order=body.sort_order)
    session.add(photo)
    await session.commit()
    return PhotoAdminOut.model_validate(photo)


@router.delete("/photos/{photo_id}", response_model=Ok)
async def delete_photo(photo_id: int, session: SessionDep, ctx: AdminDep) -> Ok:
    photo = await session.get(SalonPhoto, photo_id)
    if photo is None or photo.salon_id != ctx.salon.id:
        raise NotFound("Фото не найдено")
    await session.delete(photo)
    await session.commit()
    return Ok()


def process_image(data: bytes) -> tuple[bytes, str]:
    """Проверяет формат, поворачивает по EXIF, уменьшает до MAX_SIDE. Возвращает (байты, ext)."""
    img: Image.Image
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format or ""
        if fmt not in FORMATS:
            raise AppError("bad_image", "Поддерживаются JPEG, PNG и WebP")
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise AppError("bad_image", "Не удалось прочитать изображение") from e
    img = ImageOps.exif_transpose(img) or img
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(out, "JPEG", quality=85, optimize=True)
    elif fmt == "PNG":
        img.save(out, "PNG", optimize=True)
    else:
        img.save(out, "WEBP", quality=85)
    return out.getvalue(), FORMATS[fmt][0]


@router.post("/uploads", response_model=UploadOut, status_code=201)
async def upload(file: UploadFile, ctx: AdminDep) -> UploadOut:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError("too_large", "Файл больше 5 МБ", status_code=413)
    content, ext = await run_in_threadpool(process_image, data)
    rel = Path(str(ctx.salon.id)) / f"{uuid.uuid4().hex}.{ext}"
    target = Path(settings.uploads_dir) / rel
    await run_in_threadpool(target.parent.mkdir, parents=True, exist_ok=True)
    await run_in_threadpool(target.write_bytes, content)
    return UploadOut(url=settings.uploads_base_url.rstrip("/") + "/" + rel.as_posix())
