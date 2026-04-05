from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.keyboards.main_menu import get_main_menu_keyboard

router = Router()


SECTION_TITLES = {
    "enterprise": "🏢 О предприятии",
    "union": "🤝 Профсоюз",
    "public_orgs": "🏛 Общественные организации",
    "youth_council": "👥 Молодёжный совет",
    "about_bot": "🤖 О боте",
}

CONTACT_GROUP_TITLES = {
    "enterprise_contacts": "🏢 Контакты предприятия",
    "hr_contacts": "🧾 Отдел кадров",
    "union_contacts": "🤝 Профсоюз",
    "youth_contacts": "👥 Молодёжный совет",
}


def normalize_html_text(text: str) -> str:
    return (text or "").replace("\\n", "\n")


def get_contact_group_title(group_code: str) -> str:
    return CONTACT_GROUP_TITLES.get(group_code, "📞 Контакты")


def build_content_section_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏢 О предприятии", callback_data="section:open:enterprise")],
            [InlineKeyboardButton(text="🤝 Профсоюз", callback_data="section:open:union")],
            [InlineKeyboardButton(text="🏛 Общественные организации", callback_data="section:open:public_orgs")],
            [InlineKeyboardButton(text="⚽🏊‍♂️🏓 Расписание залов", callback_data="info:halls")],
            [InlineKeyboardButton(text="❓ FAQ", callback_data="info:faq")],
        ]
    )


def build_section_menu_keyboard(section_code: str, pages) -> InlineKeyboardMarkup:
    buttons = []

    for page in pages:
        title = page["menu_title"] or page["title"] or "Без названия"
        buttons.append([
            InlineKeyboardButton(
                text=title,
                callback_data=f"page:open:{section_code}:{page['page_id']}",
            )
        ])

    if section_code in {"enterprise", "union", "public_orgs"}:
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="info:root")])
    else:
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main:noop")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_page_keyboard(
    section_code: str,
    parent_code: str | None = None,
    child_pages=None,
) -> InlineKeyboardMarkup:
    buttons = []

    if child_pages:
        for child in child_pages:
            title = child["menu_title"] or child["title"] or "Без названия"
            buttons.append([
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"page:open:{section_code}:{child['page_id']}",
                )
            ])

    if parent_code:
        buttons.append([
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"page:open:{section_code}:{parent_code}",
            )
        ])
    else:
        if section_code in {"enterprise", "union", "public_orgs"}:
            back_callback = "info:root"
        elif section_code == "about_bot":
            back_callback = "main_menu"
        elif section_code == "youth_council":
            back_callback = "main_menu"
        else:
            back_callback = f"section:open:{section_code}"

        buttons.append([
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=back_callback,
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_info_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="info:root")]
        ]
    )


def build_contacts_root_keyboard(group_codes: list[str]) -> InlineKeyboardMarkup:
    buttons = []
    for group_code in group_codes:
        buttons.append([
            InlineKeyboardButton(
                text=get_contact_group_title(group_code),
                callback_data=f"contacts:group:{group_code}",
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_contacts_group_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="contacts:root")]
        ]
    )


def build_events_list_keyboard(rows) -> InlineKeyboardMarkup:
    buttons = []

    for row in rows:
        buttons.append([
            InlineKeyboardButton(
                text=row["title"],
                callback_data=f"events:open:{row['event_id']}",
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_event_card_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="events:list")]
        ]
    )


async def get_root_pages(db_pool, section_code: str):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                page_id,
                section_code,
                parent_code,
                menu_title,
                title,
                body_html,
                button_text,
                button_url,
                sort_order
            FROM content_pages
            WHERE active = TRUE
              AND section_code = $1
              AND (parent_code IS NULL OR parent_code = '')
            ORDER BY sort_order, id
        """, section_code)
    return rows


async def get_child_pages(db_pool, parent_code: str):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                page_id,
                section_code,
                parent_code,
                menu_title,
                title,
                body_html,
                button_text,
                button_url,
                sort_order
            FROM content_pages
            WHERE active = TRUE
              AND parent_code = $1
            ORDER BY sort_order, id
        """, parent_code)
    return rows


async def get_page_by_id(db_pool, page_id: str):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                page_id,
                section_code,
                parent_code,
                menu_title,
                title,
                body_html,
                button_text,
                button_url,
                sort_order
            FROM content_pages
            WHERE active = TRUE
              AND page_id = $1
            LIMIT 1
        """, page_id)
    return row


async def get_contact_group_codes(db_pool):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT group_code
            FROM contacts
            WHERE active = TRUE
            ORDER BY group_code
        """)
    return [row["group_code"] for row in rows if row["group_code"]]


async def get_contacts_by_group(db_pool, group_code: str):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                contact_id,
                group_code,
                department,
                person_name,
                position,
                phone,
                email,
                telegram,
                address,
                work_hours,
                note,
                sort_order
            FROM contacts
            WHERE active = TRUE
              AND group_code = $1
            ORDER BY sort_order, id
        """, group_code)
    return rows


async def get_hall_schedule(db_pool):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                slot_id,
                hall_name,
                day_of_week,
                time_from,
                time_to,
                activity,
                note,
                sort_order
            FROM hall_schedule
            WHERE active = TRUE
            ORDER BY hall_name, day_of_week, time_from, sort_order, id
        """)
    return rows


async def get_active_events(db_pool):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                event_id,
                title,
                date_start,
                date_end,
                time_start,
                time_end,
                date_precision,
                time_precision,
                date_text,
                time_text,
                sort_date,
                place,
                description,
                organizer,
                contact,
                link,
                sort_order
            FROM events
            WHERE active = TRUE
            ORDER BY
                sort_date NULLS LAST,
                sort_order,
                id
        """)
    return rows


async def get_event_by_id(db_pool, event_id: str):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                event_id,
                title,
                date_start,
                date_end,
                time_start,
                time_end,
                date_precision,
                time_precision,
                date_text,
                time_text,
                sort_date,
                place,
                description,
                organizer,
                contact,
                link,
                sort_order
            FROM events
            WHERE active = TRUE
              AND event_id = $1
            LIMIT 1
        """, event_id)
    return row


def build_event_text(row) -> str:
    parts = [f"✅ <b>{row['title']}</b>"]

    date_line = format_event_date(row)
    time_line = format_event_time(row)

    if date_line:
        parts.append(f"📅 {date_line}")

    if time_line:
        parts.append(f"🕒 {time_line}")

    if row["place"]:
        parts.append(f"📍 {row['place']}")

    if row["description"]:
        parts.append(normalize_html_text(row["description"]))

    if row["organizer"]:
        parts.append(f"👤 Организатор: {row['organizer']}")

    if row["contact"]:
        parts.append(f"📞 Контакт: {row['contact']}")

    if row["link"]:
        parts.append(f"🔗 Ссылка: {row['link']}")

    return "\n\n".join(parts).strip()


async def get_faq_items(db_pool):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                faq_id,
                category_code,
                question,
                answer_html,
                sort_order
            FROM faq_items
            WHERE active = TRUE
            ORDER BY category_code, sort_order, id
        """)
    return rows


def day_of_week_title(day: int) -> str:
    mapping = {
        1: "Понедельник",
        2: "Вторник",
        3: "Среда",
        4: "Четверг",
        5: "Пятница",
        6: "Суббота",
        7: "Воскресенье",
    }
    return mapping.get(day, f"День {day}")


MONTH_NAMES_RU = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}

MONTH_NAMES_RU_NOMINATIVE = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


def format_event_date(row) -> str:
    if row["date_text"]:
        return row["date_text"]

    date_start = row["date_start"]
    date_end = row["date_end"]
    precision = row["date_precision"]

    if precision == "none":
        return "Дата уточняется"

    if precision == "month" and date_start:
        return format_month_human(date_start)

    if date_start and date_end:
        if date_start == date_end:
            return format_date_human(date_start)

        if date_start.year == date_end.year and date_start.month == date_end.month:
            return f"{date_start.day}–{date_end.day} {MONTH_NAMES_RU[date_start.month]} {date_start.year}"

        if date_start.year == date_end.year:
            return (
                f"{date_start.day} {MONTH_NAMES_RU[date_start.month]} — "
                f"{date_end.day} {MONTH_NAMES_RU[date_end.month]} {date_end.year}"
            )

        return f"{format_date_human(date_start)} — {format_date_human(date_end)}"

    if date_start:
        return format_date_human(date_start)

    return "Дата уточняется"


def format_event_time(row) -> str:
    if row["time_text"]:
        return row["time_text"]

    time_start = row["time_start"]
    time_end = row["time_end"]
    precision = row["time_precision"]

    if precision == "all_day":
        return "Весь день"

    if time_start and time_end:
        return f"{time_start.strftime('%H:%M')}–{time_end.strftime('%H:%M')}"

    if time_start:
        return time_start.strftime("%H:%M")

    if precision == "none":
        return ""

    return ""


def format_date_human(dt) -> str:
    return f"{dt.day} {MONTH_NAMES_RU[dt.month]} {dt.year}"


def format_month_human(dt) -> str:
    return f"{MONTH_NAMES_RU_NOMINATIVE[dt.month]} {dt.year}"


def build_contact_text(row) -> str:
    parts = []

    if row["person_name"]:
        parts.append(f"<b>{row['person_name']}</b>")

    if row["position"]:
        parts.append(row["position"])

    if row["department"]:
        parts.append(f"Подразделение: {row['department']}")

    if row["phone"]:
        parts.append(f"Телефон: {row['phone']}")

    if row["email"]:
        parts.append(f"Email: {row['email']}")

    if row["telegram"]:
        parts.append(f"Telegram: {row['telegram']}")

    if row["address"]:
        parts.append(f"Адрес: {row['address']}")

    if row["work_hours"]:
        parts.append(f"Время работы: {row['work_hours']}")

    if row["note"]:
        parts.append(row["note"])

    return "\n".join(parts).strip()


async def show_info_root(message: Message):
    await message.answer(
        "📘 <b>Полезная информация</b>\n\nВыберите раздел:",
        reply_markup=build_content_section_keyboard(),
    )


async def edit_info_root(callback: CallbackQuery):
    await callback.message.edit_text(
        "📘 <b>Полезная информация</b>\n\nВыберите раздел:",
        reply_markup=build_content_section_keyboard(),
    )


async def show_section_menu(message: Message, db_pool, section_code: str):
    pages = await get_root_pages(db_pool, section_code)
    title = SECTION_TITLES.get(section_code, "Раздел")

    if not pages:
        await message.answer(
            f"{title}\n\nРаздел пока пуст.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    if len(pages) == 1:
        page = pages[0]
        child_pages = await get_child_pages(db_pool, page["page_id"])

        parts = []
        if page["title"]:
            parts.append(f"<b>{page['title']}</b>")
        if page["body_html"]:
            parts.append(normalize_html_text(page["body_html"]))

        text = "\n\n".join(parts).strip() or "Без содержимого."

        await message.answer(
            text,
            reply_markup=build_page_keyboard(
                section_code=page["section_code"],
                parent_code=page["parent_code"],
                child_pages=child_pages,
            ),
        )
        return

    await message.answer(
        f"{title}\n\nВыберите раздел:",
        reply_markup=build_section_menu_keyboard(section_code, pages),
    )

async def edit_section_menu(callback: CallbackQuery, db_pool, section_code: str):
    pages = await get_root_pages(db_pool, section_code)
    title = SECTION_TITLES.get(section_code, "Раздел")

    if not pages:
        if section_code in {"enterprise", "union", "public_orgs"}:
            back_markup = build_info_back_keyboard()
        else:
            back_markup = None

        await callback.message.edit_text(
            f"{title}\n\nРаздел пока пуст.",
            reply_markup=back_markup,
        )
        return

    if len(pages) == 1:
        page = pages[0]
        child_pages = await get_child_pages(db_pool, page["page_id"])

        parts = []
        if page["title"]:
            parts.append(f"<b>{page['title']}</b>")
        if page["body_html"]:
            parts.append(normalize_html_text(page["body_html"]))

        text = "\n\n".join(parts).strip() or "Без содержимого."

        await callback.message.edit_text(
            text,
            reply_markup=build_page_keyboard(
                section_code=page["section_code"],
                parent_code=page["parent_code"],
                child_pages=child_pages,
            ),
        )
        return

    await callback.message.edit_text(
        f"{title}\n\nВыберите раздел:",
        reply_markup=build_section_menu_keyboard(section_code, pages),
    )

async def show_page(callback: CallbackQuery, db_pool, section_code: str, page_id: str):
    page = await get_page_by_id(db_pool, page_id)

    if not page:
        await callback.answer("Страница не найдена", show_alert=True)
        return

    child_pages = await get_child_pages(db_pool, page["page_id"])

    parts = []

    if page["title"]:
        parts.append(f"<b>{page['title']}</b>")

    if page["body_html"]:
        parts.append(normalize_html_text(page["body_html"]))

    text = "\n\n".join(parts).strip() or "Без содержимого."

    await callback.message.edit_text(
        text,
        reply_markup=build_page_keyboard(
            section_code=page["section_code"],
            parent_code=page["parent_code"],
            child_pages=child_pages,
        ),
    )


async def show_contacts_root_message(message: Message, db_pool):
    group_codes = await get_contact_group_codes(db_pool)

    if not group_codes:
        await message.answer(
            "📞 <b>Контакты</b>\n\nРаздел пока пуст.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    await message.answer(
        "📞 <b>Контакты</b>\n\nВыберите раздел:",
        reply_markup=build_contacts_root_keyboard(group_codes),
    )


async def edit_contacts_root(callback: CallbackQuery, db_pool):
    group_codes = await get_contact_group_codes(db_pool)

    if not group_codes:
        await callback.message.edit_text("📞 <b>Контакты</b>\n\nРаздел пока пуст.")
        return

    await callback.message.edit_text(
        "📞 <b>Контакты</b>\n\nВыберите раздел:",
        reply_markup=build_contacts_root_keyboard(group_codes),
    )


async def show_contacts_group(callback: CallbackQuery, db_pool, group_code: str):
    rows = await get_contacts_by_group(db_pool, group_code)

    if not rows:
        await callback.message.edit_text(
            "📞 <b>Контакты</b>\n\nВ этом разделе пока нет контактов.",
            reply_markup=build_contacts_group_keyboard(),
        )
        return

    title = get_contact_group_title(group_code)
    blocks = [f"<b>{title}</b>"]

    for row in rows:
        contact_text = build_contact_text(row)
        if contact_text:
            blocks.append(contact_text)

    text = "\n\n".join(blocks).strip()

    await callback.message.edit_text(
        text,
        reply_markup=build_contacts_group_keyboard(),
    )


async def show_halls(callback: CallbackQuery, db_pool):
    rows = await get_hall_schedule(db_pool)

    if not rows:
        await callback.message.edit_text(
            "⚽🏊‍♂️🏓 <b>Расписание залов</b>\n\nРаздел пока пуст.",
            reply_markup=build_info_back_keyboard(),
        )
        return

    parts = ["⚽🏊‍♂️🏓 <b>Расписание залов</b>"]
    current_hall = None
    current_day = None

    for row in rows:
        hall_name = row["hall_name"]
        day_name = day_of_week_title(row["day_of_week"])
        time_from = row["time_from"].strftime("%H:%M")
        time_to = row["time_to"].strftime("%H:%M")

        if hall_name != current_hall:
            current_hall = hall_name
            current_day = None
            parts.append(f"\n<b>{hall_name}</b>")

        if row["day_of_week"] != current_day:
            current_day = row["day_of_week"]
            parts.append(f"\n{day_name}")

        line = f"{time_from}-{time_to} — {row['activity']}"
        if row["note"]:
            line += f" ({row['note']})"
        parts.append(line)

    await callback.message.edit_text(
        "\n".join(parts),
        reply_markup=build_info_back_keyboard(),
    )


async def show_faq(callback: CallbackQuery, db_pool):
    rows = await get_faq_items(db_pool)

    if not rows:
        await callback.message.edit_text(
            "❓ <b>FAQ</b>\n\nРаздел пока пуст.",
            reply_markup=build_info_back_keyboard(),
        )
        return

    parts = ["❓ <b>FAQ</b>"]
    current_category = None

    for row in rows:
        category = row["category_code"] or "Общее"

        if category != current_category:
            current_category = category
            parts.append(f"\n<b>{category}</b>")

        parts.append(f"\n<b>В:</b> {row['question']}")
        parts.append(f"<b>О:</b> {normalize_html_text(row['answer_html'])}")

    await callback.message.edit_text(
        "\n".join(parts),
        reply_markup=build_info_back_keyboard(),
    )


async def show_events_list_message(message: Message, db_pool):
    rows = await get_active_events(db_pool)

    if not rows:
        await message.answer(
            "📅 <b>Мероприятия</b>\n\nПока нет активных мероприятий.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    await message.answer(
        "📅 <b>Мероприятия</b>\n\nВыберите событие:",
        reply_markup=build_events_list_keyboard(rows),
    )


async def edit_events_list(callback: CallbackQuery, db_pool):
    rows = await get_active_events(db_pool)

    if not rows:
        await callback.message.edit_text(
            "📅 <b>Мероприятия</b>\n\nПока нет активных мероприятий."
        )
        return

    await callback.message.edit_text(
        "📅 <b>Мероприятия</b>\n\nВыберите событие:",
        reply_markup=build_events_list_keyboard(rows),
    )


async def show_event_card(callback: CallbackQuery, db_pool, event_id: str):
    row = await get_event_by_id(db_pool, event_id)

    if not row:
        await callback.answer("Событие не найдено", show_alert=True)
        return

    await callback.message.edit_text(
        build_event_text(row),
        reply_markup=build_event_card_keyboard(),
    )


@router.message(F.text == "📘 Полезная информация")
async def menu_useful_info(message: Message):
    await show_info_root(message)


@router.message(F.text == "👥 Молодёжный совет")
async def menu_youth_council(message: Message, db_pool):
    await show_section_menu(message, db_pool, "youth_council")


@router.message(F.text == "🤖 О боте")
async def menu_about_bot(message: Message, db_pool):
    await show_section_menu(message, db_pool, "about_bot")


@router.message(F.text == "📞 Контакты")
async def menu_contacts(message: Message, db_pool):
    await show_contacts_root_message(message, db_pool)


@router.message(F.text == "📅 Мероприятия")
async def menu_events(message: Message, db_pool):
    await show_events_list_message(message, db_pool)


@router.callback_query(F.data == "info:root")
async def callback_info_root(callback: CallbackQuery):
    await edit_info_root(callback)
    await callback.answer()


@router.callback_query(F.data == "info:halls")
async def callback_info_halls(callback: CallbackQuery, db_pool):
    await show_halls(callback, db_pool)
    await callback.answer()


@router.callback_query(F.data == "info:faq")
async def callback_info_faq(callback: CallbackQuery, db_pool):
    await show_faq(callback, db_pool)
    await callback.answer()


@router.callback_query(F.data == "contacts:root")
async def callback_contacts_root(callback: CallbackQuery, db_pool):
    await edit_contacts_root(callback, db_pool)
    await callback.answer()


@router.callback_query(F.data.startswith("contacts:group:"))
async def callback_contacts_group(callback: CallbackQuery, db_pool):
    group_code = callback.data.split(":", maxsplit=2)[2]
    await show_contacts_group(callback, db_pool, group_code)
    await callback.answer()


@router.callback_query(F.data.startswith("section:open:"))
async def callback_open_section(callback: CallbackQuery, db_pool):
    section_code = callback.data.split(":", maxsplit=2)[2]
    await edit_section_menu(callback, db_pool, section_code)
    await callback.answer()


@router.callback_query(F.data.startswith("page:open:"))
async def callback_open_page(callback: CallbackQuery, db_pool):
    parts = callback.data.split(":", maxsplit=3)
    if len(parts) != 4:
        await callback.answer("Некорректная команда", show_alert=True)
        return

    section_code = parts[2]
    page_id = parts[3]

    await show_page(callback, db_pool, section_code, page_id)
    await callback.answer()


@router.callback_query(F.data == "events:list")
async def callback_events_list(callback: CallbackQuery, db_pool):
    await edit_events_list(callback, db_pool)
    await callback.answer()


@router.callback_query(F.data.startswith("events:open:"))
async def callback_events_open(callback: CallbackQuery, db_pool):
    event_id = callback.data.split(":", maxsplit=2)[2]
    await show_event_card(callback, db_pool, event_id)
    await callback.answer()


@router.callback_query(F.data == "main:noop")
async def callback_main_noop(callback: CallbackQuery):
    await callback.answer()

@router.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "Возврат в главное меню.",
        reply_markup=None,
    )
    await callback.message.answer(
        "Выберите раздел:",
        reply_markup=get_main_menu_keyboard(),
    )
    await callback.answer()