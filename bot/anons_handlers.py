# bot/anons_handlers.py
import asyncio
import html
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Optional, Tuple, List

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from bot.db import upsert_user
import bot.db as dbmod  # используем текущий pool из bot/db.py (dbmod._pool)

router = Router()

# -------------------------
# Helpers
# -------------------------
def _pool():
    # Используем текущую архитектуру без добавления новых слоёв:
    # init_db() уже создаёт dbmod._pool в bot/db.py
    if getattr(dbmod, "_pool", None) is None:
        raise RuntimeError("DB pool is not initialized. Ensure init_db() is called before handlers.")
    return dbmod._pool


def is_admin(telegram_id: int) -> bool:
    raw = os.getenv("ADMIN_IDS", "").strip()
    if not raw:
        return False
    admin_ids = {int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}
    return telegram_id in admin_ids


def _now_utc():
    return datetime.utcnow()


def _valid_url(url: str) -> bool:
    url = (url or "").strip()
    if not url:
        return False
    # минимальная проверка
    return bool(re.match(r"^https?://", url, flags=re.IGNORECASE))


# -------------------------
# HTML sanitizer (whitelist)
# Allowed tags: b, i, u, a(href), code, pre, br
# -------------------------
ALLOWED_TAGS = {"b", "i", "u", "a", "code", "pre", "br"}
ALLOWED_A_ATTRS = {"href"}


class _SafeHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out: List[str] = []
        self.stack: List[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            return


        if tag == "a":
            attrs_dict = {k.lower(): v for k, v in attrs if k and v}
            href = attrs_dict.get("href", "")
            if not _valid_url(href):
                # если ссылка невалидна — игнорируем тег, но текст внутри оставим
                self.stack.append("__skip_a__")
                return
            safe_href = html.escape(href, quote=True)
            self.out.append(f'<a href="{safe_href}">')
            self.stack.append("a")
            return

        self.out.append(f"<{tag}>")
        self.stack.append(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag not in ALLOWED_TAGS or tag == "br":
            return

        if not self.stack:
            return

        top = self.stack.pop()
        if top == "__skip_a__":
            return

        # закрываем только то, что реально открывали
        if top == tag:
            self.out.append(f"</{tag}>")
        else:
            # если стек разъехался — мягко игнорируем закрытие
            # (чтобы не падать на кривом вводе)
            return

    def handle_data(self, data):
        self.out.append(html.escape(data))

    def handle_entityref(self, name):
        self.out.append(f"&{name};")

    def handle_charref(self, name):
        self.out.append(f"&#{name};")

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()


    def get_html(self) -> str:
        # закрываем незакрытые (кроме skip)
        while self.stack:
            t = self.stack.pop()
            if t in ("__skip_a__", "br"):
                continue
            self.out.append(f"</{t}>")
        return "".join(self.out)


def sanitize_html(text: str) -> str:
    text = (text or "").strip()
    parser = _SafeHTML()
    try:
        parser.feed(text)
        parser.close()
        return parser.get_html().strip()
    except Exception:
        # если совсем криво — экранируем всё
        return html.escape(text)


# -------------------------
# DB schema expectations
# (таблицы должны быть созданы отдельно)
# announcements(id, created_at, created_by, text_html, photo_file_id, button_text, button_url, status, posted_at,
#              preview_chat_id, preview_message_id, sent_job_started_at, sent_job_finished_at)
# announcement_stats(announcement_id, total_target, sent_ok, sent_fail, blocked_count)
# announcement_clicks(id, announcement_id, telegram_id, clicked_at)
# users(..., is_blocked)
# -------------------------
async def db_create_draft(created_by: int) -> int:
    row = await _pool().fetchrow(
        "INSERT INTO announcements (created_by, status) VALUES ($1, 'draft') RETURNING id",
        created_by,
    )
    return int(row["id"])


async def db_get_announcement(ann_id: int):
    return await _pool().fetchrow("SELECT * FROM announcements WHERE id=$1", ann_id)


async def db_update_text(ann_id: int, text_html: str):
    await _pool().execute(
        "UPDATE announcements SET text_html=$2 WHERE id=$1",
        ann_id,
        text_html,
    )


async def db_update_photo(ann_id: int, photo_file_id: Optional[str]):
    await _pool().execute(
        "UPDATE announcements SET photo_file_id=$2 WHERE id=$1",
        ann_id,
        photo_file_id,
    )


async def db_update_button(ann_id: int, button_text: Optional[str], button_url: Optional[str]):
    await _pool().execute(
        "UPDATE announcements SET button_text=$2, button_url=$3 WHERE id=$1",
        ann_id,
        button_text,
        button_url,
    )


async def db_set_preview_msg(ann_id: int, chat_id: int, message_id: int):
    await _pool().execute(
        "UPDATE announcements SET preview_chat_id=$2, preview_message_id=$3 WHERE id=$1",
        ann_id,
        chat_id,
        message_id,
    )


async def db_cancel(ann_id: int):
    await _pool().execute(
        "UPDATE announcements SET status='canceled' WHERE id=$1 AND status='draft'",
        ann_id,
    )


async def db_try_mark_sending(ann_id: int) -> bool:
    row = await _pool().fetchrow(
        """
        UPDATE announcements
        SET sent_job_started_at=now()
        WHERE id=$1
          AND status='draft'
          AND sent_job_started_at IS NULL
        RETURNING id
        """,
        ann_id,
    )
    return row is not None


async def db_mark_posted(ann_id: int):
    await _pool().execute(
        """
        UPDATE announcements
        SET status='posted', posted_at=now(), sent_job_finished_at=now()
        WHERE id=$1
        """,
        ann_id,
    )


async def db_save_stats(ann_id: int, total: int, ok: int, fail: int, blocked: int):
    await _pool().execute(
        """
        INSERT INTO announcement_stats(announcement_id, total_target, sent_ok, sent_fail, blocked_count)
        VALUES($1,$2,$3,$4,$5)
        ON CONFLICT (announcement_id) DO UPDATE
          SET total_target=EXCLUDED.total_target,
              sent_ok=EXCLUDED.sent_ok,
              sent_fail=EXCLUDED.sent_fail,
              blocked_count=EXCLUDED.blocked_count
        """,
        ann_id,
        total,
        ok,
        fail,
        blocked,
    )


async def db_click_add(ann_id: int, telegram_id: int):
    await _pool().execute(
        "INSERT INTO announcement_clicks(announcement_id, telegram_id) VALUES($1,$2)",
        ann_id,
        telegram_id,
    )


async def db_click_count(ann_id: int) -> int:
    row = await _pool().fetchrow(
        "SELECT count(*)::int AS c FROM announcement_clicks WHERE announcement_id=$1",
        ann_id,
    )
    return int(row["c"] or 0)


async def db_stats_get(ann_id: int):
    return await _pool().fetchrow(
        "SELECT * FROM announcement_stats WHERE announcement_id=$1",
        ann_id,
    )


async def db_posted_list(offset: int, limit: int = 10):
    return await _pool().fetch(
        """
        SELECT id, posted_at, created_at, created_by, text_html, photo_file_id, button_text, button_url
        FROM announcements
        WHERE status='posted'
        ORDER BY posted_at DESC NULLS LAST, created_at DESC
        OFFSET $1 LIMIT $2
        """,
        offset,
        limit,
    )


async def db_copy_as_new_draft(source_ann_id: int, created_by: int) -> int:
    row = await _pool().fetchrow(
        """
        INSERT INTO announcements (created_by, text_html, photo_file_id, button_text, button_url, status)
        SELECT $2, text_html, photo_file_id, button_text, button_url, 'draft'
        FROM announcements
        WHERE id=$1
        RETURNING id
        """,
        source_ann_id,
        created_by,
    )
    return int(row["id"])


# -------------------------
# Keyboards
# -------------------------
def kb_photo_step(ann_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Без фото", callback_data=f"anons_nophoto:{ann_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"anons_cancel:{ann_id}")],
        ]
    )


def kb_link_step(ann_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустить", callback_data=f"anons_skiplink:{ann_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"anons_cancel:{ann_id}")],
        ]
    )


def kb_preview_controls(ann_id: int, has_photo: bool, has_button: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="✅ Отправить всем", callback_data=f"anons_send:{ann_id}")],
        [
            InlineKeyboardButton(text="✏️ Изменить текст", callback_data=f"anons_edit_text:{ann_id}"),
            InlineKeyboardButton(text="🖼️ Изменить фото", callback_data=f"anons_edit_photo:{ann_id}"),
        ],
        [InlineKeyboardButton(text="🔗 Изменить ссылку “Записаться”", callback_data=f"anons_edit_link:{ann_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"anons_cancel:{ann_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_history_page(offset: int, has_more: bool) -> InlineKeyboardMarkup:
    buttons = []
    if offset > 0:
        buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"anons_hist:{max(0, offset-10)}"))
    if has_more:
        buttons.append(InlineKeyboardButton(text="Следующие ▶️", callback_data=f"anons_hist:{offset+10}"))
    rows = [buttons] if buttons else []
    rows.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="anons_hist_close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_history_item(ann_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📄 Посмотреть", callback_data=f"anons_view:{ann_id}"),
                InlineKeyboardButton(text="🔁 Скопировать как черновик", callback_data=f"anons_copy:{ann_id}"),
            ]
        ]
    )


def kb_join_button(ann_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Записаться", callback_data=f"anons_join:{ann_id}")]
        ]
    )


# -------------------------
# FSM
# -------------------------
class AnonsState(StatesGroup):
    waiting_text = State()
    waiting_photo = State()
    waiting_link = State()
    editing_text = State()
    editing_photo = State()
    editing_link = State()


# -------------------------
# Preview rendering (edit same message if possible)
# -------------------------
@dataclass
class PreviewData:
    text_html: str
    photo_file_id: Optional[str]
    has_button: bool


async def _build_preview(ann_row) -> PreviewData:
    text_html = (ann_row["text_html"] or "").strip()
    photo = ann_row["photo_file_id"]
    btn_text = ann_row["button_text"]
    btn_url = ann_row["button_url"]
    has_button = bool(btn_text and btn_url)
    return PreviewData(text_html=text_html, photo_file_id=photo, has_button=has_button)


async def _send_or_edit_preview(
    bot: Bot,
    ann_id: int,
    chat_id: int,
    preview: PreviewData,
    message_id: Optional[int],
):
    # Кнопка "Записаться" должна быть callback, чтобы считать клики.
    reply_markup = kb_join_button(ann_id) if preview.has_button else None
    controls = kb_preview_controls(ann_id, has_photo=bool(preview.photo_file_id), has_button=preview.has_button)

    # превью: текст+фото (если есть). Контролы — отдельной inline клавиатурой под сообщением превью.
    # Telegram не умеет две клавиатуры одновременно, поэтому объединяем:
    # - если есть join-кнопка, ставим её первой строкой, затем controls
    if preview.has_button:
        joined = InlineKeyboardMarkup(
            inline_keyboard=kb_join_button(ann_id).inline_keyboard + controls.inline_keyboard
        )
        final_kb = joined
    else:
        final_kb = controls

    try:
        if preview.photo_file_id:
            # фото + caption
            caption = preview.text_html[:1024]  # Telegram caption limit
            media = InputMediaPhoto(media=preview.photo_file_id, caption=caption, parse_mode="HTML")
            if message_id:
                try:
                    await bot.edit_message_media(
                        chat_id=chat_id,
                        message_id=message_id,
                        media=media,
                        reply_markup=final_kb,
                    )
                    return message_id
                except TelegramBadRequest:
                    # нельзя отредактировать медиа (например тип сообщения другой) — шлём заново
                    pass

            msg = await bot.send_photo(
                chat_id=chat_id,
                photo=preview.photo_file_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=final_kb,
            )
            await db_set_preview_msg(ann_id, chat_id, msg.message_id)
            return msg.message_id

        else:
            # только текст
            if message_id:
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=preview.text_html or " ",
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                        reply_markup=final_kb,
                    )
                    return message_id
                except TelegramBadRequest as e:
                    # MessageNotModified / can't edit / etc.
                    if "message is not modified" in str(e).lower():
                        return message_id
                    pass

            msg = await bot.send_message(
                chat_id=chat_id,
                text=preview.text_html or " ",
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=final_kb,
            )
            await db_set_preview_msg(ann_id, chat_id, msg.message_id)
            return msg.message_id

    except TelegramBadRequest:
        # fallback: отправим новое сообщение
        msg = await bot.send_message(
            chat_id=chat_id,
            text=preview.text_html or " ",
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=final_kb,
        )
        await db_set_preview_msg(ann_id, chat_id, msg.message_id)
        return msg.message_id


# -------------------------
# Broadcast (rate limited + blocked)
# -------------------------
async def broadcast_announcement(bot: Bot, ann_id: int) -> Tuple[int, int, int, int]:
    ann = await db_get_announcement(ann_id)
    if not ann:
        return 0, 0, 0, 0

    preview = await _build_preview(ann)

    # В рассылке кнопка "Записаться" — callback. Ссылку (если нужна) отправим отдельным сообщением при клике.
    has_join = bool(ann["button_text"] and ann["button_url"])
    join_kb = kb_join_button(ann_id) if has_join else None

    # speed limit
    rate_delay = float(os.getenv("ANONS_RATE_DELAY", "0.1"))  # 10 msg/sec default

    rows = await _pool().fetch("SELECT telegram_id FROM users WHERE is_blocked=false")
    total = len(rows)
    ok = fail = blocked = 0

    for r in rows:
        uid = int(r["telegram_id"])
        try:
            if preview.photo_file_id:
                await bot.send_photo(
                    chat_id=uid,
                    photo=preview.photo_file_id,
                    caption=preview.text_html[:1024],
                    parse_mode="HTML",
                    reply_markup=join_kb,
                )
            else:
                await bot.send_message(
                    chat_id=uid,
                    text=preview.text_html,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=join_kb,
                )
            ok += 1

        except TelegramRetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 0.5)
            fail += 1

        except TelegramForbiddenError:
            blocked += 1
            await _pool().execute("UPDATE users SET is_blocked=true WHERE telegram_id=$1", uid)

        except TelegramBadRequest as e:
            msg = str(e).lower()
            if "chat not found" in msg:
                blocked += 1
                await _pool().execute("UPDATE users SET is_blocked=true WHERE telegram_id=$1", uid)
            else:
                fail += 1

        except Exception:
            fail += 1

        await asyncio.sleep(rate_delay)

    return total, ok, fail, blocked


# -------------------------
# /anons flow
# -------------------------
@router.message(Command("anons"))
async def anons_start(message: Message, state: FSMContext):
    u = message.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    if not is_admin(u.id):
        return

    ann_id = await db_create_draft(u.id)
    await state.update_data(ann_id=ann_id)

    await state.set_state(AnonsState.waiting_text)
    await message.answer(
        "📝 <b>Создание анонса</b>\n"
        "Отправь текст анонса (HTML разрешён: <b>b</b>, <i>i</i>, <u>u</u>, <code>code</code>, <pre>pre</pre>, <a href=\"https://...\">ссылка</a>). Перенос строки — просто Enter.",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(AnonsState.waiting_text)
async def anons_text_step(message: Message, state: FSMContext):
    u = message.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    data = await state.get_data()
    ann_id = data.get("ann_id")
    if not ann_id:
        await state.clear()
        return

    raw = (message.text or "").strip()
    if len(raw) < 3:
        await message.answer("Текст слишком короткий. Пришли нормальный текст анонса.")
        return
    if len(raw) > 3500:
        await message.answer("Слишком длинно. Укороти текст (до ~3500 символов).")
        return

    safe = sanitize_html(raw)
    await db_update_text(int(ann_id), safe)

    await state.set_state(AnonsState.waiting_photo)
    await message.answer(
        "🖼️ <b>Фото</b>\nПришли фото для анонса или нажми «Без фото».",
        parse_mode="HTML",
        reply_markup=kb_photo_step(int(ann_id)),
    )


@router.callback_query(F.data.startswith("anons_nophoto:"))
async def anons_no_photo(call: CallbackQuery, state: FSMContext):
    u = call.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    ann_id = int(call.data.split(":", 1)[1])
    if not is_admin(u.id):
        await call.answer()
        return

    await db_update_photo(ann_id, None)
    await state.update_data(ann_id=ann_id)
    await state.set_state(AnonsState.waiting_link)

    await call.message.edit_text(
        "🔗 <b>Кнопка “Записаться”</b>\n"
        "Пришли URL (https://...), чтобы добавить кнопку. Или нажми «Пропустить».",
        parse_mode="HTML",
        reply_markup=kb_link_step(ann_id),
        disable_web_page_preview=True,
    )
    await call.answer()


@router.message(AnonsState.waiting_photo, F.photo)
async def anons_photo_step(message: Message, state: FSMContext):
    u = message.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    data = await state.get_data()
    ann_id = int(data.get("ann_id") or 0)
    if not ann_id:
        await state.clear()
        return

    if not is_admin(u.id):
        return

    # берём самое большое фото
    file_id = message.photo[-1].file_id
    await db_update_photo(ann_id, file_id)

    await state.set_state(AnonsState.waiting_link)
    await message.answer(
        "🔗 <b>Кнопка “Записаться”</b>\n"
        "Пришли URL (https://...), чтобы добавить кнопку. Или нажми «Пропустить».",
        parse_mode="HTML",
        reply_markup=kb_link_step(ann_id),
        disable_web_page_preview=True,
    )


@router.message(AnonsState.waiting_photo)
async def anons_photo_wrong(message: Message, state: FSMContext):
    # ждём фото или кнопку "без фото"
    await message.answer("Пришли фото (как photo) или нажми «Без фото».")


@router.callback_query(F.data.startswith("anons_skiplink:"))
async def anons_skip_link(call: CallbackQuery, state: FSMContext):
    u = call.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    ann_id = int(call.data.split(":", 1)[1])
    if not is_admin(u.id):
        await call.answer()
        return

    await db_update_button(ann_id, None, None)

    ann = await db_get_announcement(ann_id)
    prev = await _build_preview(ann)

    # отправляем/редактируем превью тем же сообщением
    message_id = ann["preview_message_id"]
    new_mid = await _send_or_edit_preview(call.bot, ann_id, call.message.chat.id, prev, message_id)
    await db_set_preview_msg(ann_id, call.message.chat.id, new_mid)

    await state.clear()
    await call.answer("Превью обновлено")


@router.message(AnonsState.waiting_link)
async def anons_link_step(message: Message, state: FSMContext):
    u = message.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    data = await state.get_data()
    ann_id = int(data.get("ann_id") or 0)
    if not ann_id:
        await state.clear()
        return

    if not is_admin(u.id):
        return

    url = (message.text or "").strip()
    if not _valid_url(url):
        await message.answer("Некорректная ссылка. Нужен URL вида https://... Или нажми «Пропустить».")
        return

    # храним button_url, а button_text фиксированный
    await db_update_button(ann_id, "✅ Записаться", url)

    ann = await db_get_announcement(ann_id)
    prev = await _build_preview(ann)
    mid = ann["preview_message_id"]
    new_mid = await _send_or_edit_preview(message.bot, ann_id, message.chat.id, prev, mid)
    await db_set_preview_msg(ann_id, message.chat.id, new_mid)

    await state.clear()
    await message.answer("✅ Черновик готов. Используй кнопки под превью.", disable_web_page_preview=True)


# -------------------------
# Preview controls: edit/cancel/send
# -------------------------
@router.callback_query(F.data.startswith("anons_cancel:"))
async def anons_cancel(call: CallbackQuery, state: FSMContext):
    u = call.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    ann_id = int(call.data.split(":", 1)[1])
    if not is_admin(u.id):
        await call.answer()
        return

    await db_cancel(ann_id)
    await state.clear()

    try:
        await call.message.edit_text("❌ <b>Анонс отменён</b>", parse_mode="HTML")
    except TelegramBadRequest:
        await call.message.answer("❌ Анонс отменён", disable_web_page_preview=True)

    await call.answer()


@router.callback_query(F.data.startswith("anons_edit_text:"))
async def anons_edit_text(call: CallbackQuery, state: FSMContext):
    u = call.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    ann_id = int(call.data.split(":", 1)[1])
    if not is_admin(u.id):
        await call.answer()
        return

    await state.update_data(ann_id=ann_id)
    await state.set_state(AnonsState.editing_text)
    await call.message.answer("✏️ Пришли новый текст анонса (HTML whitelist).", disable_web_page_preview=True)
    await call.answer()


@router.message(AnonsState.editing_text)
async def anons_edit_text_apply(message: Message, state: FSMContext):
    u = message.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    if not is_admin(u.id):
        await state.clear()
        return

    data = await state.get_data()
    ann_id = int(data.get("ann_id") or 0)
    if not ann_id:
        await state.clear()
        return

    raw = (message.text or "").strip()
    if len(raw) < 3:
        await message.answer("Текст слишком короткий.")
        return
    if len(raw) > 3500:
        await message.answer("Слишком длинно. Укороти текст.")
        return

    safe = sanitize_html(raw)
    await db_update_text(ann_id, safe)

    ann = await db_get_announcement(ann_id)
    prev = await _build_preview(ann)
    mid = ann["preview_message_id"]
    new_mid = await _send_or_edit_preview(message.bot, ann_id, ann["preview_chat_id"] or message.chat.id, prev, mid)
    await db_set_preview_msg(ann_id, ann["preview_chat_id"] or message.chat.id, new_mid)

    await state.clear()
    await message.answer("✅ Текст обновлён.", disable_web_page_preview=True)


@router.callback_query(F.data.startswith("anons_edit_photo:"))
async def anons_edit_photo(call: CallbackQuery, state: FSMContext):
    u = call.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    ann_id = int(call.data.split(":", 1)[1])
    if not is_admin(u.id):
        await call.answer()
        return

    await state.update_data(ann_id=ann_id)
    await state.set_state(AnonsState.editing_photo)
    await call.message.answer("🖼️ Пришли новое фото или отправь текст: Без фото", disable_web_page_preview=True)
    await call.answer()


@router.message(AnonsState.editing_photo, F.photo)
async def anons_edit_photo_apply(message: Message, state: FSMContext):
    u = message.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    if not is_admin(u.id):
        await state.clear()
        return

    data = await state.get_data()
    ann_id = int(data.get("ann_id") or 0)
    if not ann_id:
        await state.clear()
        return

    file_id = message.photo[-1].file_id
    await db_update_photo(ann_id, file_id)

    ann = await db_get_announcement(ann_id)
    prev = await _build_preview(ann)
    mid = ann["preview_message_id"]
    new_mid = await _send_or_edit_preview(message.bot, ann_id, ann["preview_chat_id"] or message.chat.id, prev, mid)
    await db_set_preview_msg(ann_id, ann["preview_chat_id"] or message.chat.id, new_mid)

    await state.clear()
    await message.answer("✅ Фото обновлено.", disable_web_page_preview=True)


@router.message(AnonsState.editing_photo)
async def anons_edit_photo_no(message: Message, state: FSMContext):
    u = message.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    if not is_admin(u.id):
        await state.clear()
        return

    data = await state.get_data()
    ann_id = int(data.get("ann_id") or 0)
    if not ann_id:
        await state.clear()
        return

    txt = (message.text or "").strip().lower()
    if txt in ("без фото", "no photo", "nophoto"):
        await db_update_photo(ann_id, None)

        ann = await db_get_announcement(ann_id)
        prev = await _build_preview(ann)
        mid = ann["preview_message_id"]
        new_mid = await _send_or_edit_preview(message.bot, ann_id, ann["preview_chat_id"] or message.chat.id, prev, mid)
        await db_set_preview_msg(ann_id, ann["preview_chat_id"] or message.chat.id, new_mid)

        await state.clear()
        await message.answer("✅ Фото удалено.", disable_web_page_preview=True)
        return

    await message.answer("Пришли фото или напиши: Без фото")


@router.callback_query(F.data.startswith("anons_edit_link:"))
async def anons_edit_link(call: CallbackQuery, state: FSMContext):
    u = call.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    ann_id = int(call.data.split(":", 1)[1])
    if not is_admin(u.id):
        await call.answer()
        return

    await state.update_data(ann_id=ann_id)
    await state.set_state(AnonsState.editing_link)
    await call.message.answer(
        "🔗 Пришли новый URL (https://...) или напиши: Без кнопки",
        disable_web_page_preview=True
    )
    await call.answer()


@router.message(AnonsState.editing_link)
async def anons_edit_link_apply(message: Message, state: FSMContext):
    u = message.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    if not is_admin(u.id):
        await state.clear()
        return

    data = await state.get_data()
    ann_id = int(data.get("ann_id") or 0)
    if not ann_id:
        await state.clear()
        return

    txt = (message.text or "").strip()
    if txt.lower() in ("без кнопки", "no button", "nobutton"):
        await db_update_button(ann_id, None, None)
    else:
        if not _valid_url(txt):
            await message.answer("Некорректная ссылка. Нужен https://... или напиши: Без кнопки")
            return
        await db_update_button(ann_id, "✅ Записаться", txt)

    ann = await db_get_announcement(ann_id)
    prev = await _build_preview(ann)
    mid = ann["preview_message_id"]
    new_mid = await _send_or_edit_preview(message.bot, ann_id, ann["preview_chat_id"] or message.chat.id, prev, mid)
    await db_set_preview_msg(ann_id, ann["preview_chat_id"] or message.chat.id, new_mid)

    await state.clear()
    await message.answer("✅ Ссылка обновлена.", disable_web_page_preview=True)


@router.callback_query(F.data.startswith("anons_send:"))
async def anons_send(call: CallbackQuery):
    u = call.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    ann_id = int(call.data.split(":", 1)[1])
    if not is_admin(u.id):
        await call.answer()
        return

    # идемпотентность: захватываем рассылку
    locked = await db_try_mark_sending(ann_id)
    if not locked:
        await call.answer("Уже отправляется или уже отправлено.", show_alert=True)
        return

    await call.answer("Отправляю…")

    total, ok, fail, blocked = await broadcast_announcement(call.bot, ann_id)
    await db_save_stats(ann_id, total, ok, fail, blocked)
    await db_mark_posted(ann_id)

    clicks = await db_click_count(ann_id)
    txt = (
        "✅ <b>Анонс отправлен</b>\n"
        f"Всего: <b>{total}</b>\n"
        f"Успешно: <b>{ok}</b>\n"
        f"Ошибок: <b>{fail}</b>\n"
        f"Заблокировали: <b>{blocked}</b>\n"
        f"Кликов “Записаться”: <b>{clicks}</b>"
    )

    try:
        await call.message.edit_text(txt, parse_mode="HTML", disable_web_page_preview=True)
    except TelegramBadRequest:
        await call.message.answer(txt, parse_mode="HTML", disable_web_page_preview=True)


# -------------------------
# Join callback (click metric + send URL separately)
# -------------------------
@router.callback_query(F.data.startswith("anons_join:"))
async def anons_join(call: CallbackQuery):
    u = call.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    ann_id = int(call.data.split(":", 1)[1])

    # фиксируем клик
    try:
        await db_click_add(ann_id, u.id)
    except Exception:
        pass

    ann = await db_get_announcement(ann_id)
    url = (ann["button_url"] or "").strip() if ann else ""

    # нейтральный ответ
    await call.answer("Принято")

    # если есть реальная ссылка — пришлём отдельным сообщением
    if _valid_url(url):
        try:
            await call.message.answer(f"🔗 Ссылка для записи:\n{url}", disable_web_page_preview=True)
        except Exception:
            pass


# -------------------------
# History
# -------------------------
@router.message(Command("anons_history"))
async def anons_history(message: Message):
    u = message.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)

    if not is_admin(u.id):
        return

    await _send_history_page(message, offset=0)


async def _send_history_page(message: Message, offset: int):
    rows = await db_posted_list(offset=offset, limit=10)
    has_more = len(rows) == 10

    if not rows and offset == 0:
        await message.answer("История пустая.", disable_web_page_preview=True)
        return

    lines = ["📚 <b>История анонсов</b>"]
    for r in rows:
        ann_id = int(r["id"])
        posted_at = r["posted_at"] or r["created_at"]
        dt = posted_at.strftime("%d.%m.%Y %H:%M")
        # короткий заголовок из первых 60 символов текста (без тегов)
        raw = re.sub(r"<[^>]+>", "", (r["text_html"] or ""))
        raw = " ".join(raw.split()).strip()
        title = raw[:60] + ("…" if len(raw) > 60 else "")
        lines.append(f"\n<b>#{ann_id}</b> — {dt}\n{html.escape(title)}")

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=kb_history_page(offset=offset, has_more=has_more),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("anons_hist:"))
async def anons_hist_page(call: CallbackQuery):
    u = call.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)
    if not is_admin(u.id):
        await call.answer()
        return

    offset = int(call.data.split(":", 1)[1])
    rows = await db_posted_list(offset=offset, limit=10)
    has_more = len(rows) == 10

    lines = ["📚 <b>История анонсов</b>"]
    for r in rows:
        ann_id = int(r["id"])
        posted_at = r["posted_at"] or r["created_at"]
        dt = posted_at.strftime("%d.%m.%Y %H:%M")
        raw = re.sub(r"<[^>]+>", "", (r["text_html"] or ""))
        raw = " ".join(raw.split()).strip()
        title = raw[:60] + ("…" if len(raw) > 60 else "")
        lines.append(f"\n<b>#{ann_id}</b> — {dt}\n{html.escape(title)}")

    try:
        await call.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=kb_history_page(offset=offset, has_more=has_more),
            disable_web_page_preview=True,
        )
    except TelegramBadRequest:
        pass

    await call.answer()


@router.callback_query(F.data == "anons_hist_close")
async def anons_hist_close(call: CallbackQuery):
    await call.answer()
    try:
        await call.message.delete()
    except Exception:
        pass


@router.callback_query(F.data.startswith("anons_view:"))
async def anons_view(call: CallbackQuery):
    u = call.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)
    if not is_admin(u.id):
        await call.answer()
        return

    ann_id = int(call.data.split(":", 1)[1])
    ann = await db_get_announcement(ann_id)
    if not ann:
        await call.answer("Не найдено", show_alert=True)
        return

    stats = await db_stats_get(ann_id)
    clicks = await db_click_count(ann_id)

    total = int(stats["total_target"]) if stats else 0
    ok = int(stats["sent_ok"]) if stats else 0
    fail = int(stats["sent_fail"]) if stats else 0
    blocked = int(stats["blocked_count"]) if stats else 0

    header = (
        f"📄 <b>Анонс #{ann_id}</b>\n"
        f"Отправлено: <b>{ok}</b> / <b>{total}</b>\n"
        f"Ошибок: <b>{fail}</b>\n"
        f"Блокировок: <b>{blocked}</b>\n"
        f"Кликов “Записаться”: <b>{clicks}</b>\n\n"
    )

    # покажем содержимое отдельным сообщением (не пытаемся редактировать историю)
    # если фото — отправим фото + caption
    if ann["photo_file_id"]:
        await call.message.answer_photo(
            photo=ann["photo_file_id"],
            caption=(header + (ann["text_html"] or ""))[:1024],
            parse_mode="HTML",
            disable_notification=True,
        )
        if ann["button_text"] and ann["button_url"]:
            await call.message.answer(
                f"🔗 Ссылка записи:\n{ann['button_url']}",
                disable_web_page_preview=True
            )
    else:
        await call.message.answer(
            header + (ann["text_html"] or ""),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    await call.message.answer(
        f"Действия для <b>#{ann_id}</b>:",
        parse_mode="HTML",
        reply_markup=kb_history_item(ann_id),
        disable_web_page_preview=True,
    )
    await call.answer()


@router.callback_query(F.data.startswith("anons_copy:"))
async def anons_copy(call: CallbackQuery):
    u = call.from_user
    await upsert_user(u.id, u.username, u.first_name, u.last_name)
    if not is_admin(u.id):
        await call.answer()
        return

    src_id = int(call.data.split(":", 1)[1])
    new_id = await db_copy_as_new_draft(src_id, u.id)

    ann = await db_get_announcement(new_id)
    prev = await _build_preview(ann)
    mid = ann["preview_message_id"]
    new_mid = await _send_or_edit_preview(call.bot, new_id, call.message.chat.id, prev, mid)
    await db_set_preview_msg(new_id, call.message.chat.id, new_mid)

    await call.message.answer(
        f"✅ Скопировано как новый черновик: <b>#{new_id}</b>",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await call.answer()
