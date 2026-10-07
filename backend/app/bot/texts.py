"""Все тексты бота."""

from html import escape

from app.models import Appointment, NotificationKind
from app.services.formatting import fmt_datetime, fmt_price

WELCOME = (
    "Здравствуйте! 👋\n\n"
    "Здесь можно записаться в салон и управлять своими записями.\n"
    "Чтобы записаться, откройте ссылку салона или нажмите кнопку ниже."
)
BTN_MY_APPOINTMENTS = "Мои записи"
BTN_OPEN_CABINET = "Открыть кабинет"
BTN_OPEN_SCHEDULE = "Открыть расписание"
BTN_CONFIRM = "✅ Приду"
BTN_RESCHEDULE = "🔁 Перенести"
BTN_MAP = "🗺 Как добраться"

CONTACT_SAVED = "Спасибо! Телефон получен — вернитесь в приложение, чтобы завершить запись."
CONTACT_FOREIGN = "Пожалуйста, отправьте свой контакт кнопкой «Поделиться номером»."

CONFIRMED_SUFFIX = "\n\n✅ <b>Вы подтвердили визит. Ждём вас!</b>"
CONFIRM_OK = "Спасибо, ждём вас!"
CONFIRM_FAILED = "Не удалось подтвердить запись"


def invite_accepted(salon_name: str) -> str:
    return (
        f"Вы добавлены в салон «{escape(salon_name)}» 🎉\n\n"
        "В кабинете можно смотреть расписание, вести записи и настраивать график."
    )


def invite_error(message: str) -> str:
    return f"⚠️ {escape(message)}"


def _details(appt: Appointment, *, with_address: bool, with_price: bool) -> list[str]:
    salon = appt.salon
    lines = [
        f"<b>{escape(salon.name)}</b>",
        f"Услуга: {escape(appt.service.name)}",
        f"Мастер: {escape(appt.staff.display_name)}",
        f"Когда: {fmt_datetime(appt.starts_at, salon.timezone)}",
    ]
    if with_address and salon.address:
        lines.append(f"Адрес: {escape(salon.address)}")
    if with_price:
        lines.append(f"Стоимость: {fmt_price(appt.price, appt.price_is_from)}")
    return lines


def _staff_details(appt: Appointment) -> list[str]:
    tz = appt.salon.timezone
    lines = [
        f"Клиент: {escape(appt.client.name)}",
        f"Телефон: {escape(appt.client.phone)}",
        f"Услуга: {escape(appt.service.name)}",
        f"Когда: {fmt_datetime(appt.starts_at, tz)}",
    ]
    if appt.comment:
        lines.append(f"Комментарий: {escape(appt.comment)}")
    return lines


def notification_text(kind: NotificationKind, appt: Appointment) -> str:
    if kind == NotificationKind.client_booked:
        head = "✅ Вы записаны"
        body = _details(appt, with_address=True, with_price=True)
        tail = ["", "Напомним о визите заранее."]
        return "\n".join([head, "", *body, *tail])
    if kind == NotificationKind.reminder_24h:
        head = "⏰ Напоминаем: завтра у вас запись"
        return "\n".join([head, "", *_details(appt, with_address=True, with_price=False)])
    if kind == NotificationKind.reminder_2h:
        head = "⏰ Через 2 часа у вас запись"
        return "\n".join([head, "", *_details(appt, with_address=True, with_price=False)])
    if kind == NotificationKind.client_cancelled_by_salon:
        lines = [
            "❌ Салон отменил вашу запись",
            "",
            *_details(appt, with_address=False, with_price=False),
        ]
        if appt.salon.phone:
            lines += ["", f"Телефон салона: {escape(appt.salon.phone)}"]
        return "\n".join(lines)
    if kind == NotificationKind.staff_new:
        return "\n".join(["🆕 Новая запись", "", *_staff_details(appt)])
    if kind == NotificationKind.staff_rescheduled:
        return "\n".join(["🔁 Запись перенесена", "", *_staff_details(appt)])
    if kind == NotificationKind.staff_cancelled:
        return "\n".join(["❌ Клиент отменил запись", "", *_staff_details(appt)])
    raise ValueError(f"unknown kind {kind}")
