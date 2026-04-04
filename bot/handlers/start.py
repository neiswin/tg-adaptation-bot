from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.db import get_user, set_onboarding_completed, upsert_user
from bot.keyboards.main_menu import get_main_menu_keyboard

router = Router()


def _normalize_html_text(text: str) -> str:
    return (text or "").replace("\\n", "\n")


def get_onboarding_keyboard(index: int, total: int) -> InlineKeyboardMarkup:
    buttons = []

    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"welcome:prev:{index}"))
    if index < total - 1:
        nav_row.append(InlineKeyboardButton(text="➡️ Далее", callback_data=f"welcome:next:{index}"))
    if index == total - 1:
        nav_row.append(InlineKeyboardButton(text="🏠 В меню", callback_data="welcome:finish"))

    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(text="⏭ Пропустить", callback_data="welcome:skip")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def load_active_slides(db_pool):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT slide_id, order_no, title, body_html, button_text, button_url
            FROM welcome_slides
            WHERE active = TRUE
            ORDER BY order_no, id
        """)
    return rows


async def send_welcome_slide(target, db_pool, index: int):
    slides = await load_active_slides(db_pool)

    if not slides:
        await target.answer(
            "👋 <b>Добро пожаловать</b>",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    if index < 0:
        index = 0
    if index >= len(slides):
        index = len(slides) - 1

    slide = slides[index]

    text_parts = []
    if slide["title"]:
        text_parts.append(f"👋 <b>{slide['title']}</b>")
    if slide["body_html"]:
        text_parts.append(_normalize_html_text(slide["body_html"]))

    text = "\n\n".join(text_parts).strip() or "👋 <b>Добро пожаловать</b>"

    reply_markup = get_onboarding_keyboard(index, len(slides))

    if isinstance(target, Message):
        await target.answer(text, reply_markup=reply_markup)
    else:
        await target.message.edit_text(text, reply_markup=reply_markup)


@router.message(CommandStart())
async def cmd_start(message: Message, db_pool):
    await upsert_user(
        db_pool,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )

    user = await get_user(db_pool, message.from_user.id)

    if user and user["onboarding_completed"]:
        await message.answer(
            "🏠 <b>Главное меню</b>",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    await send_welcome_slide(message, db_pool, 0)


@router.callback_query(F.data.startswith("welcome:next:"))
async def onboarding_next(callback: CallbackQuery, db_pool):
    index = int(callback.data.split(":")[2])
    await send_welcome_slide(callback, db_pool, index + 1)
    await callback.answer()


@router.callback_query(F.data.startswith("welcome:prev:"))
async def onboarding_prev(callback: CallbackQuery, db_pool):
    index = int(callback.data.split(":")[2])
    await send_welcome_slide(callback, db_pool, index - 1)
    await callback.answer()


@router.callback_query(F.data == "welcome:skip")
async def onboarding_skip(callback: CallbackQuery, db_pool):
    await set_onboarding_completed(db_pool, callback.from_user.id)
    await callback.message.answer(
        "🏠 <b>Главное меню</b>",
        reply_markup=get_main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "welcome:finish")
async def onboarding_finish(callback: CallbackQuery, db_pool):
    await set_onboarding_completed(db_pool, callback.from_user.id)
    await callback.message.answer(
        "🏠 <b>Главное меню</b>",
        reply_markup=get_main_menu_keyboard(),
    )
    await callback.answer()