import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from dotenv import load_dotenv

from bot.db import init_db, close_db, upsert_user, get_user_stats

from bot.content_events import load_events, format_upcoming,  format_events_page

from bot.anons_handlers import router as anons_router


load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🗓 Мероприятия")],
            [KeyboardButton(text="🧭 Путеводитель")],
            [KeyboardButton(text="❓ FAQ")],
            [KeyboardButton(text="ℹ️ О боте")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите раздел",
    )


def is_admin(telegram_id: int) -> bool:
    raw = os.getenv("ADMIN_IDS", "").strip()
    if not raw:
        return False
    admin_ids = {int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}
    return telegram_id in admin_ids


def guide_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="\u200b🚌  Быт и инфраструктура", callback_data="guide:life")],
            [InlineKeyboardButton(text="\u200b🏢  Структура предприятия", callback_data="guide:structure")],
            [InlineKeyboardButton(text="\u200b🧾  Документы и ссылки", callback_data="guide:docs")],
            [InlineKeyboardButton(text="\u200b🧑‍🤝‍🧑  Молодёжный совет", callback_data="guide:youth")],
            [InlineKeyboardButton(text="\u200b🇧🇾  БРСМ", callback_data="guide:brsm")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="guide:back_main")],
        ]
    )


def guide_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="guide:back_guide")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="guide:home")],
        ]
    )


async def guide_callback(call: CallbackQuery):
    # учёт пользователя
    u = call.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    data = call.data or ""

    if data == "guide:back_main":
        # просто закрываем путеводитель и подсказываем, что меню снизу
        await call.message.edit_text(
            "🏠 <b>Главное меню</b>\nВыберите раздел кнопками ниже.",
            parse_mode="HTML",
            reply_markup=None
        )
        await call.answer()
        return

    if data == "guide:back_guide":
        await call.message.edit_text(
            "🧭 <b>Путеводитель</b>\nВыберите раздел:",
            parse_mode="HTML",
            reply_markup=guide_menu_kb()
        )
        await call.answer()
        return

    if data == "guide:home":
        await call.message.edit_text(
            "🏠 <b>Главное меню</b>\nВыберите раздел кнопками ниже.",
            parse_mode="HTML",
            reply_markup=None
        )
        await call.answer()
        return

    # Заглушки для разделов
    if data.startswith("guide:"):
        await call.message.edit_text(
            "🚧 <b>Раздел в разработке</b>\nСкоро добавим материалы.",
            parse_mode="HTML",
            reply_markup=guide_back_kb()
        )
        await call.answer()
        return

    await call.answer()


EVENTS_PAGE_SIZE = 5

def events_pager_kb(offset: int, total: int, page_size: int = EVENTS_PAGE_SIZE) -> InlineKeyboardMarkup | None:
    buttons = []

    prev_offset = max(0, offset - page_size)
    next_offset = offset + page_size

    if offset > 0:
        buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"events_page:{prev_offset}"))

    if next_offset < total:
        buttons.append(InlineKeyboardButton(text="Следующие ▶️", callback_data=f"events_page:{next_offset}"))

    if not buttons:
        return None

    return InlineKeyboardMarkup(inline_keyboard=[buttons])

async def track_user(message: Message) -> None:
    u = message.from_user
    await upsert_user(
        telegram_id=u.id,
        username=u.username,
        first_name=u.first_name,
        last_name=u.last_name,
    )


async def start_handler(message: Message):
    await track_user(message)
    await message.answer(
        "Привет! Я бот адаптации молодых работников.\n"
        "Выберите раздел в меню ниже.",
        reply_markup=main_menu(),
    )


async def stats_handler(message: Message):
    await track_user(message)

    u = message.from_user
    if not is_admin(u.id):
        return  # молча игнорируем не-админов

    s = await get_user_stats()
    await message.answer(
        "📊 Статистика бота\n"
        f"Всего пользователей: {s['total']}\n"
        f"Активные за 7 дней: {s['active_7d']}\n"
        f"Активные за 30 дней: {s['active_30d']}"
    )


async def events_handler(message: Message):
    await track_user(message)

    events = await load_events()
    text, total, shown = format_events_page(events, offset=0, limit=EVENTS_PAGE_SIZE)

    kb = events_pager_kb(offset=0, total=total)

    await message.answer(
        text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=kb
    )

async def events_page_callback(call: CallbackQuery):
    # обновим last_seen
    u = call.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    try:
        offset = int(call.data.split(":", 1)[1])
    except Exception:
        await call.answer()
        return

    events = await load_events()
    text, total, shown = format_events_page(events, offset=offset, limit=EVENTS_PAGE_SIZE)
    kb = events_pager_kb(offset=offset, total=total)

    await call.message.edit_text(
        text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=kb
    )
    await call.answer()



async def guide_handler(message: Message):
    await track_user(message)
    await message.answer(
        "🧭 <b>Путеводитель</b>\nВыберите раздел:",
        parse_mode="HTML",
        reply_markup=guide_menu_kb()
    )


# async def contacts_handler(message: Message):
#     await track_user(message)
#     await message.answer("Раздел «Контакты». Пока без данных.")


async def faq_handler(message: Message):
    await track_user(message)
    await message.answer("Раздел «FAQ». Пока без данных.")


async def about_handler(message: Message):
    await track_user(message)
    await message.answer(
        "Бот Молодёжного совета: справка по адаптации, мероприятиям и контактам.\n"
        "В разработке."
    )

async def reload_handler(message: Message):
    await track_user(message)

    u = message.from_user
    if not is_admin(u.id):
        return

    await load_events(force=True)
    await message.answer("✅ Контент обновлён (events).")



async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not found")

    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(anons_router)

    dp.message.register(start_handler, CommandStart())
    dp.message.register(stats_handler, Command("stats"))

    dp.message.register(events_handler, F.text == "🗓 Мероприятия")

    dp.message.register(faq_handler, F.text == "❓ FAQ")
    dp.message.register(about_handler, F.text == "ℹ️ О боте")

    dp.message.register(reload_handler, Command("reload"))
    dp.callback_query.register(events_page_callback, F.data.startswith("events_page:"))

    dp.message.register(guide_handler, F.text == "🧭 Путеводитель")
    dp.callback_query.register(guide_callback, F.data.startswith("guide:"))


    try:
        await dp.start_polling(bot)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
