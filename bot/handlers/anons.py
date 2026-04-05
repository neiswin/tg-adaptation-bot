from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.utils.formatting import Text

from bot.config import settings

import asyncio
import html
import re

router = Router()


class AnonsState(StatesGroup):
    waiting_text = State()
    waiting_photo = State()
    editing_text = State()
    editing_photo = State()


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def sanitize_html(text: str) -> str:
    text = (text or "").strip()
    text = text.replace("\\n", "\n")
    return text


def valid_http_url(url: str) -> bool:
    return bool(re.match(r"^https?://", (url or "").strip(), flags=re.IGNORECASE))


def build_photo_step_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Без фото", callback_data="anons:nophoto")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="anons:cancel")],
        ]
    )

def build_preview_keyboard(has_photo: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="✅ Отправить всем", callback_data="anons:send")],
        [InlineKeyboardButton(text="✏️ Изменить текст", callback_data="anons:edit_text")],
        [InlineKeyboardButton(text="🖼 Изменить фото", callback_data="anons:edit_photo")],
    ]

    if has_photo:
        rows.append([InlineKeyboardButton(text="🗑 Удалить фото", callback_data="anons:remove_photo")])

    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="anons:cancel")])

    return InlineKeyboardMarkup(inline_keyboard=rows)

def telegram_message_to_html(message: Message) -> str:
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []

    if not entities:
        return html.escape(text).replace("\n", "\n")

    entity_map = {}

    for ent in entities:
        start = ent.offset
        end = ent.offset + ent.length

        open_tag = ""
        close_tag = ""

        if ent.type == "bold":
            open_tag, close_tag = "<b>", "</b>"
        elif ent.type == "italic":
            open_tag, close_tag = "<i>", "</i>"
        elif ent.type == "underline":
            open_tag, close_tag = "<u>", "</u>"
        elif ent.type == "strikethrough":
            open_tag, close_tag = "<s>", "</s>"
        elif ent.type == "spoiler":
            open_tag, close_tag = "<tg-spoiler>", "</tg-spoiler>"
        elif ent.type == "code":
            open_tag, close_tag = "<code>", "</code>"
        elif ent.type == "pre":
            open_tag, close_tag = "<pre>", "</pre>"
        elif ent.type == "text_link" and ent.url:
            open_tag, close_tag = f'<a href="{html.escape(ent.url, quote=True)}">', "</a>"
        elif ent.type == "url":
            url_text = text[start:end]
            open_tag, close_tag = f'<a href="{html.escape(url_text, quote=True)}">', "</a>"
        else:
            continue

        entity_map.setdefault(start, {"open": [], "close": []})
        entity_map.setdefault(end, {"open": [], "close": []})

        entity_map[start]["open"].append(open_tag)
        entity_map[end]["close"].insert(0, close_tag)

    result = []
    for i, ch in enumerate(text):
        if i in entity_map:
            result.extend(entity_map[i]["open"])

        result.append(html.escape(ch))

        if i + 1 in entity_map:
            result.extend(entity_map[i + 1]["close"])

    return "".join(result)

async def create_draft(pool, created_by: int) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO announcements (created_by, status)
            VALUES ($1, 'draft')
            RETURNING id
        """, created_by)
        return int(row["id"])


async def update_draft_text(pool, ann_id: int, text_html: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE announcements
            SET text_html = $2
            WHERE id = $1
        """, ann_id, text_html)


async def update_draft_photo(pool, ann_id: int, photo_file_id: str | None):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE announcements
            SET photo_file_id = $2
            WHERE id = $1
        """, ann_id, photo_file_id)


async def get_draft(pool, ann_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT *
            FROM announcements
            WHERE id = $1
            LIMIT 1
        """, ann_id)


async def save_preview_message(pool, ann_id: int, chat_id: int, message_id: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE announcements
            SET preview_chat_id = $2,
                preview_message_id = $3
            WHERE id = $1
        """, ann_id, chat_id, message_id)


async def cancel_draft(pool, ann_id: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE announcements
            SET status = 'canceled'
            WHERE id = $1 AND status = 'draft'
        """, ann_id)


async def try_mark_sending(pool, ann_id: int) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            UPDATE announcements
            SET sent_job_started_at = now()
            WHERE id = $1
              AND status = 'draft'
              AND sent_job_started_at IS NULL
            RETURNING id
        """, ann_id)
        return row is not None


async def mark_posted(pool, ann_id: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE announcements
            SET status = 'posted',
                posted_at = now(),
                sent_job_finished_at = now()
            WHERE id = $1
        """, ann_id)


async def save_stats(pool, ann_id: int, total: int, ok: int, fail: int, blocked: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO announcement_stats (
                announcement_id, total_target, sent_ok, sent_fail, blocked_count
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (announcement_id) DO UPDATE
            SET total_target = EXCLUDED.total_target,
                sent_ok = EXCLUDED.sent_ok,
                sent_fail = EXCLUDED.sent_fail,
                blocked_count = EXCLUDED.blocked_count
        """, ann_id, total, ok, fail, blocked)


async def render_preview(message: Message, draft) -> Message:
    text_html = draft["text_html"] or " "
    photo_file_id = draft["photo_file_id"]

    if photo_file_id:
        return await message.answer_photo(
            photo=photo_file_id,
            caption=text_html[:1024],
            parse_mode="HTML",
            reply_markup=build_preview_keyboard(has_photo=True),
        )

    return await message.answer(
        text_html,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=build_preview_keyboard(has_photo=False),
    )


async def broadcast_announcement(bot, pool, draft) -> tuple[int, int, int, int]:
    total = ok = fail = blocked = 0

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT telegram_id
            FROM users
            WHERE is_blocked = FALSE
        """)

    total = len(rows)
    text_html = draft["text_html"] or " "
    photo_file_id = draft["photo_file_id"]

    for row in rows:
        user_id = int(row["telegram_id"])

        try:
            if photo_file_id:
                await bot.send_photo(
                    chat_id=user_id,
                    photo=photo_file_id,
                    caption=text_html[:1024],
                    parse_mode="HTML",
                )
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=text_html,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            ok += 1

        except TelegramRetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 0.5)
            fail += 1

        except TelegramForbiddenError:
            blocked += 1
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE users
                    SET is_blocked = TRUE
                    WHERE telegram_id = $1
                """, user_id)

        except TelegramBadRequest as e:
            if "chat not found" in str(e).lower():
                blocked += 1
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE users
                        SET is_blocked = TRUE
                        WHERE telegram_id = $1
                    """, user_id)
            else:
                fail += 1

        except Exception:
            fail += 1

        await asyncio.sleep(0.08)

    return total, ok, fail, blocked

async def refresh_preview(callback: CallbackQuery, db_pool, ann_id: int):
    draft = await get_draft(db_pool, ann_id)

    text_html = draft["text_html"] or " "
    photo_file_id = draft["photo_file_id"]

    if photo_file_id:
        # если текущее сообщение уже с фото, лучше отправить новое превью
        preview_msg = await callback.message.answer_photo(
            photo=photo_file_id,
            caption=text_html[:1024],
            parse_mode="HTML",
            reply_markup=build_preview_keyboard(has_photo=True),
        )
    else:
        preview_msg = await callback.message.answer(
            text_html,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=build_preview_keyboard(has_photo=False),
        )

    await save_preview_message(db_pool, ann_id, preview_msg.chat.id, preview_msg.message_id)



@router.message(Command("anons"))
async def anons_start(message: Message, state: FSMContext, db_pool):
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к этой команде.")
        return

    ann_id = await create_draft(db_pool, message.from_user.id)
    await state.update_data(ann_id=ann_id)
    await state.set_state(AnonsState.waiting_text)

    await message.answer(
        "📝 Отправь текст анонса.\n\n"
        "Можно использовать форматирование сообщений:\n"
    )

@router.message(AnonsState.waiting_text)
async def anons_text_step(message: Message, state: FSMContext, db_pool):
    data = await state.get_data()
    ann_id = int(data["ann_id"])

    if not (message.text or message.caption):
        await message.answer("Нужен текст анонса.")
        return

    text = telegram_message_to_html(message)

    if len((message.text or message.caption or "").strip()) < 3:
        await message.answer("Текст слишком короткий.")
        return

    await update_draft_text(db_pool, ann_id, text)
    await state.set_state(AnonsState.waiting_photo)

    await message.answer(
        "🖼 Пришли фото для анонса или нажми «Без фото».",
        reply_markup=build_photo_step_keyboard(),
    )


@router.message(AnonsState.waiting_photo, F.photo)
@router.message(AnonsState.editing_photo, F.photo)
async def anons_photo_step(message: Message, state: FSMContext, db_pool):
    data = await state.get_data()
    ann_id = int(data["ann_id"])

    file_id = message.photo[-1].file_id
    await update_draft_photo(db_pool, ann_id, file_id)

    draft = await get_draft(db_pool, ann_id)
    preview_msg = await render_preview(message, draft)
    await save_preview_message(db_pool, ann_id, preview_msg.chat.id, preview_msg.message_id)

    await state.set_state(None)


@router.callback_query(F.data == "anons:nophoto")
async def anons_no_photo(callback: CallbackQuery, state: FSMContext, db_pool):
    data = await state.get_data()
    ann_id = int(data["ann_id"])

    await update_draft_photo(db_pool, ann_id, None)

    draft = await get_draft(db_pool, ann_id)
    preview_msg = await render_preview(callback.message, draft)
    await save_preview_message(db_pool, ann_id, preview_msg.chat.id, preview_msg.message_id)

    await state.set_state(None)
    await callback.answer()

@router.callback_query(F.data == "anons:cancel")
async def anons_cancel(callback: CallbackQuery, state: FSMContext, db_pool):
    data = await state.get_data()
    ann_id = data.get("ann_id")

    if ann_id:
        await cancel_draft(db_pool, int(ann_id))

    await state.clear()
    await callback.message.edit_text("❌ Анонс отменён.")
    await callback.answer()


@router.callback_query(F.data == "anons:send")
async def anons_send(callback: CallbackQuery, state: FSMContext, db_pool):
    data = await state.get_data()
    ann_id = data.get("ann_id")

    if not ann_id:
        await callback.answer("Черновик не найден", show_alert=True)
        return

    ann_id = int(ann_id)

    locked = await try_mark_sending(db_pool, ann_id)
    if not locked:
        await callback.answer("Этот анонс уже отправляется или был отправлен.", show_alert=True)
        return

    draft = await get_draft(db_pool, ann_id)

    await callback.message.edit_reply_markup(reply_markup=None)
    progress = await callback.message.answer("📣 Начинаю рассылку...")

    total, ok, fail, blocked = await broadcast_announcement(callback.bot, db_pool, draft)
    await save_stats(db_pool, ann_id, total, ok, fail, blocked)
    await mark_posted(db_pool, ann_id)

    await progress.edit_text(
        "✅ Рассылка завершена.\n\n"
        f"Всего: {total}\n"
        f"Успешно: {ok}\n"
        f"Ошибки: {fail}\n"
        f"Заблокировали бота: {blocked}"
    )

    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "anons:edit_text")
async def anons_edit_text(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AnonsState.editing_text)
    await callback.message.answer("✏️ Отправь новый текст анонса.")
    await callback.answer()

@router.message(AnonsState.editing_text)
async def anons_edit_text_step(message: Message, state: FSMContext, db_pool):
    data = await state.get_data()
    ann_id = int(data["ann_id"])

    if not (message.text or message.caption):
        await message.answer("Нужен текст анонса.")
        return

    text = telegram_message_to_html(message)

    if len((message.text or message.caption or "").strip()) < 3:
        await message.answer("Текст слишком короткий.")
        return

    await update_draft_text(db_pool, ann_id, text)
    await state.set_state(None)

    draft = await get_draft(db_pool, ann_id)
    preview_msg = await render_preview(message, draft)
    await save_preview_message(db_pool, ann_id, preview_msg.chat.id, preview_msg.message_id)

@router.callback_query(F.data == "anons:edit_photo")
async def anons_edit_photo(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AnonsState.editing_photo)
    await callback.message.answer(
        "🖼 Пришли новое фото или нажми «Без фото».",
        reply_markup=build_photo_step_keyboard(),
    )
    await callback.answer()

@router.callback_query(F.data == "anons:remove_photo")
async def anons_remove_photo(callback: CallbackQuery, state: FSMContext, db_pool):
    data = await state.get_data()
    ann_id = data.get("ann_id")

    if not ann_id:
        await callback.answer("Черновик не найден", show_alert=True)
        return

    ann_id = int(ann_id)

    await update_draft_photo(db_pool, ann_id, None)

    draft = await get_draft(db_pool, ann_id)
    text_html = draft["text_html"] or " "

    await callback.message.answer(
        text_html,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=build_preview_keyboard(has_photo=False),
    )

    await callback.answer("Фото удалено")