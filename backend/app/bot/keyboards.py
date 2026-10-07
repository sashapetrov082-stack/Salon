from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.bot import texts
from app.config import settings
from app.models import Appointment, AppointmentStatus, NotificationKind

CONFIRM_PREFIX = "ap:c:"

CLIENT_REMINDERS = (NotificationKind.reminder_24h, NotificationKind.reminder_2h)
STAFF_KINDS = (
    NotificationKind.staff_new,
    NotificationKind.staff_rescheduled,
    NotificationKind.staff_cancelled,
)


def webapp_button(text: str, start_param: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text, web_app=WebAppInfo(url=settings.miniapp_link(start_param))
    )


def open_app() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[webapp_button(texts.BTN_MY_APPOINTMENTS)]])


def open_cabinet(salon_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[webapp_button(texts.BTN_OPEN_CABINET, f"m_{salon_id}")]]
    )


def reminder(appt: Appointment, *, confirmed: bool = False) -> InlineKeyboardMarkup:
    row: list[InlineKeyboardButton] = []
    if not confirmed:
        row.append(
            InlineKeyboardButton(text=texts.BTN_CONFIRM, callback_data=f"{CONFIRM_PREFIX}{appt.id}")
        )
    row.append(webapp_button(texts.BTN_RESCHEDULE, f"r_{appt.id}"))
    rows = [row]
    if appt.salon.map_url:
        rows.append([InlineKeyboardButton(text=texts.BTN_MAP, url=appt.salon.map_url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def for_notification(kind: NotificationKind, appt: Appointment) -> InlineKeyboardMarkup | None:
    if kind in CLIENT_REMINDERS:
        return reminder(appt, confirmed=appt.status == AppointmentStatus.confirmed)
    if kind in STAFF_KINDS:
        return InlineKeyboardMarkup(
            inline_keyboard=[[webapp_button(texts.BTN_OPEN_SCHEDULE, f"m_{appt.salon_id}")]]
        )
    if kind == NotificationKind.client_booked:
        rows = [[webapp_button(texts.BTN_MY_APPOINTMENTS)]]
        if appt.salon.map_url:
            rows.append([InlineKeyboardButton(text=texts.BTN_MAP, url=appt.salon.map_url)])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    return None
