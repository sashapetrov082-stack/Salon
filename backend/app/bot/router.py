import logging
from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.types import User as TgUser
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.api.deps import upsert_user
from app.bot import keyboards, texts
from app.errors import AppError
from app.models import Appointment, User, UserContact
from app.services import booking, invites
from app.services.formatting import mask_phone, normalize_phone
from app.services.telegram_auth import TelegramWebAppUser

log = logging.getLogger(__name__)
router = Router(name="main")


async def _user(session: AsyncSession, tg: TgUser) -> User:
    return await upsert_user(
        session,
        TelegramWebAppUser(
            id=tg.id,
            first_name=tg.first_name,
            last_name=tg.last_name,
            username=tg.username,
            language_code=tg.language_code,
        ),
    )


@router.message(CommandStart())
async def on_start(
    message: Message, command: CommandObject, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    if message.from_user is None:
        return
    args = (command.args or "").strip()
    async with sessionmaker() as session:
        user = await _user(session, message.from_user)
        if user.bot_blocked:
            user.bot_blocked = False
            await session.commit()
        if args.startswith("inv_"):
            try:
                staff, salon = await invites.accept_invite(
                    session, args[4:], user, datetime.now(UTC)
                )
            except AppError as e:
                await message.answer(
                    texts.invite_error(e.message), reply_markup=keyboards.open_app()
                )
                return
            log.info("invite accepted", extra={"staff_id": staff.id, "salon_id": salon.id})
            await message.answer(
                texts.invite_accepted(salon.name), reply_markup=keyboards.open_cabinet(salon.id)
            )
            return
    await message.answer(texts.WELCOME, reply_markup=keyboards.open_app())


@router.message(F.contact)
async def on_contact(message: Message, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    contact = message.contact
    if contact is None or message.from_user is None:
        return
    if contact.user_id != message.from_user.id:
        await message.answer(texts.CONTACT_FOREIGN)
        return
    phone = normalize_phone(contact.phone_number)
    if phone is None:
        await message.answer(texts.CONTACT_FOREIGN)
        return
    async with sessionmaker() as session:
        user = await _user(session, message.from_user)
        now = datetime.now(UTC)
        await session.execute(
            insert(UserContact)
            .values(user_id=user.id, phone=phone, received_at=now)
            .on_conflict_do_update(
                index_elements=[UserContact.user_id],
                set_={"phone": phone, "received_at": now, "updated_at": now},
            )
        )
        await session.commit()
    log.info("contact received", extra={"user_id": user.id, "phone": mask_phone(phone)})
    await message.answer(texts.CONTACT_SAVED, reply_markup=ReplyKeyboardRemove())


@router.callback_query(F.data.startswith(keyboards.CONFIRM_PREFIX))
async def on_confirm(
    callback: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    try:
        appointment_id = int((callback.data or "").removeprefix(keyboards.CONFIRM_PREFIX))
    except ValueError:
        await callback.answer(texts.CONFIRM_FAILED)
        return
    async with sessionmaker() as session:
        user = await _user(session, callback.from_user)
        try:
            await booking.confirm_by_client(session, user, appointment_id, datetime.now(UTC))
        except AppError as e:
            await callback.answer(e.message, show_alert=True)
            return
        appt = await session.get(
            Appointment, appointment_id, options=[selectinload(Appointment.salon)]
        )
        assert appt is not None
        markup = keyboards.reminder(appt, confirmed=True)
    await callback.answer(texts.CONFIRM_OK)
    msg = callback.message
    if isinstance(msg, Message) and msg.html_text:
        text = msg.html_text
        if texts.CONFIRMED_SUFFIX.strip() not in text:
            text += texts.CONFIRMED_SUFFIX
        try:
            await msg.edit_text(text, reply_markup=markup)
        except Exception:  # сообщение могло быть уже изменено
            log.debug("edit failed", exc_info=True)
