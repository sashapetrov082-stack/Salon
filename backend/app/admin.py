"""Веб-админка суперадмина платформы (SQLAdmin) на /admin."""

import hashlib
import hmac
from datetime import UTC, datetime

from fastapi import FastAPI
from markupsafe import Markup
from sqladmin import Admin, ModelView, action
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from wtforms.validators import Regexp

from app.config import settings
from app.db import SessionLocal, engine
from app.models import (
    Appointment,
    Notification,
    Salon,
    Staff,
    StaffInvite,
    User,
)
from app.services import invites


def admin_secret_key() -> str:
    material = f"{settings.bot_token}:{settings.admin_password}:sqladmin".encode()
    return hashlib.sha256(material).hexdigest()


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = str(form.get("username") or "")
        password = str(form.get("password") or "")
        if not settings.admin_username or not settings.admin_password:
            return False
        ok = hmac.compare_digest(username, settings.admin_username) and hmac.compare_digest(
            password, settings.admin_password
        )
        if ok:
            request.session.update({"admin": True})
        return ok

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("admin"))


class SalonAdmin(ModelView, model=Salon):
    name = "Салон"
    name_plural = "Салоны"
    icon = "fa-solid fa-store"
    column_list = [Salon.id, Salon.name, Salon.slug, Salon.is_active, Salon.created_at]
    column_searchable_list = [Salon.name, Salon.slug]
    column_sortable_list = [Salon.id, Salon.name, Salon.created_at]
    form_excluded_columns = [Salon.photos, Salon.created_at, Salon.updated_at]
    form_args = {
        "slug": {
            "validators": [
                Regexp(
                    r"^[a-z0-9][a-z0-9-]{1,48}$", message="Латиница в нижнем регистре, цифры, дефис"
                )
            ]
        }
    }
    column_formatters_detail = {
        "slug": lambda m, a: Markup("{0} — <code>{1}</code>").format(
            m.slug, settings.salon_link(m.slug)
        )
    }


class StaffAdmin(ModelView, model=Staff):
    name = "Сотрудник"
    name_plural = "Сотрудники"
    icon = "fa-solid fa-user-tie"
    column_list = [
        Staff.id,
        Staff.salon,
        Staff.display_name,
        Staff.role,
        Staff.user,
        Staff.is_active,
    ]
    column_searchable_list = [Staff.display_name]
    form_columns = [
        Staff.salon,
        Staff.display_name,
        Staff.role,
        Staff.is_bookable,
        Staff.is_active,
        Staff.sort_order,
    ]

    @action(
        name="invite",
        label="Создать приглашение",
        confirmation_message="Создать ссылку-приглашение для выбранных сотрудников?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def create_invites(self, request: Request) -> Response:
        pks = [int(pk) for pk in request.query_params.get("pks", "").split(",") if pk]
        async with SessionLocal() as session:
            for pk in pks:
                staff = await session.get(Staff, pk)
                if staff is not None and staff.user_id is None:
                    await invites.create_invite(session, staff, datetime.now(UTC))
            await session.commit()
        return RedirectResponse(request.url_for("admin:list", identity="staff-invite"), 302)


class StaffInviteAdmin(ModelView, model=StaffInvite):
    name = "Приглашение"
    name_plural = "Приглашения"
    icon = "fa-solid fa-link"
    can_create = False
    can_edit = False
    column_list = [
        StaffInvite.id,
        StaffInvite.salon,
        StaffInvite.staff,
        StaffInvite.token,
        StaffInvite.expires_at,
        StaffInvite.used_at,
    ]
    column_default_sort = [(StaffInvite.id, True)]
    column_formatters = {
        "token": lambda m, a: Markup("<code>{0}</code>").format(settings.invite_link(m.token))
    }
    column_formatters_detail = column_formatters


class ReadOnlyView(ModelView):
    can_create = False
    can_edit = False
    can_delete = False
    can_export = False


class UserAdmin(ReadOnlyView, model=User):
    name = "Пользователь"
    name_plural = "Пользователи"
    icon = "fa-solid fa-user"
    column_list = [
        User.id,
        User.telegram_id,
        User.first_name,
        User.last_name,
        User.username,
        User.bot_blocked,
        User.created_at,
    ]
    column_searchable_list = [User.username, User.first_name, User.last_name]


class AppointmentAdmin(ReadOnlyView, model=Appointment):
    name = "Запись"
    name_plural = "Записи"
    icon = "fa-solid fa-calendar"
    column_list = [
        Appointment.id,
        Appointment.salon,
        Appointment.staff,
        Appointment.service,
        Appointment.starts_at,
        Appointment.status,
        Appointment.source,
    ]
    column_details_exclude_list = [Appointment.client]
    column_default_sort = [(Appointment.starts_at, True)]


class NotificationAdmin(ReadOnlyView, model=Notification):
    name = "Уведомление"
    name_plural = "Уведомления"
    icon = "fa-solid fa-bell"
    column_list = [
        Notification.id,
        Notification.appointment_id,
        Notification.kind,
        Notification.send_at,
        Notification.status,
        Notification.attempts,
        Notification.last_error,
    ]
    column_default_sort = [(Notification.id, True)]


def setup_admin(app: FastAPI) -> Admin:
    admin = Admin(
        app,
        engine=engine,
        title="Салоны — админка",
        authentication_backend=AdminAuth(secret_key=admin_secret_key()),
    )
    for view in (
        SalonAdmin,
        StaffAdmin,
        StaffInviteAdmin,
        UserAdmin,
        AppointmentAdmin,
        NotificationAdmin,
    ):
        admin.add_view(view)
    return admin
