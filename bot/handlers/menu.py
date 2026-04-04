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
            [InlineKeyboardButton(text="🏐 Расписание залов", callback_data="info:halls")],
            [InlineKeyboardButton(text="❓ FAQ", callback_data="info:faq")],
        ]
    )


def build_section_menu_keyboard(section_code: str, pages) -> InlineKeyboardMarkup:
    buttons = []

    for page in pages:
        button_title = page["menu_title"] or page["title"] or page["page_id"]
        buttons.append([
            InlineKeyboardButton(
                text=button_title,
                callback_data=f"page:open:{section_code}:{page['page_id']}",
            )
        ])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="info:root")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_page_keyboard(section_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"section:open:{section_code}")],
            [InlineKeyboardButton(text="📘 В полезную информацию", callback_data="info:root")],
        ]
    )


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


async def get_section_pages(db_pool, section_code: str):
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
            ORDER BY sort_order, id
        """, section_code)
    return rows


async def get_page_by_id(db_pool, section_code: str, page_id: str):
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
              AND section_code = $1
              AND page_id = $2
            LIMIT 1
        """, section_code, page_id)
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


async def sync_events(conn, rows: list[dict]):
    items = []
    for row in rows:
        event_id = as_text(row.get("event_id"))
        if not event_id:
            continue

        items.append({
            "event_id": event_id,
            "title": as_text(row.get("title")),

            "date_start": as_optional_date_value(row.get("date_start")),
            "date_end": as_optional_date_value(row.get("date_end")),
            "time_start": as_optional_time_value(row.get("time_start")),
            "time_end": as_optional_time_value(row.get("time_end")),

            "date_precision": as_text(row.get("date_precision")) or "day",
            "time_precision": as_text(row.get("time_precision")) or "none",

            "date_text": as_optional_text(row.get("date_text")),
            "time_text": as_optional_text(row.get("time_text")),
            "sort_date": as_optional_date_value(row.get("sort_date")),

            "place": as_optional_text(row.get("place")),
            "description": as_optional_text(row.get("description")),
            "organizer": as_optional_text(row.get("organizer")),
            "contact": as_optional_text(row.get("contact")),
            "link": as_optional_text(row.get("link")),

            "active": as_bool(row.get("active")),
            "sort_order": as_int(row.get("sort_order")),
        })

    async with conn.transaction():
        await conn.execute("DELETE FROM events")
        for item in items:
            await conn.execute("""
                INSERT INTO events (
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
                    active,
                    sort_order,
                    updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9,
                    $10, $11, $12, $13, $14, $15, $16,
                    $17, $18, now()
                )
            """,
            item["event_id"],
            item["title"],
            item["date_start"],
            item["date_end"],
            item["time_start"],
            item["time_end"],
            item["date_precision"],
            item["time_precision"],
            item["date_text"],
            item["time_text"],
            item["sort_date"],
            item["place"],
            item["description"],
            item["organizer"],
            item["contact"],
            item["link"],
            item["active"],
            item["sort_order"])


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



def build_event_text(row) -> str:
    parts = [f"<b>{row['title']}</b>"]

    date_line = format_event_date(row)
    time_line = format_event_time(row)

    if date_line and time_line:
        parts.append(f"{date_line}, {time_line}")
    elif date_line:
        parts.append(date_line)
    elif time_line:
        parts.append(time_line)

    if row["place"]:
        parts.append(f"<b>Место</b>: {row['place']}")

    if row["description"]:
        parts.append(normalize_html_text(row["description"]))

    if row["organizer"]:
        parts.append(f"<b>Организатор</b>: {row['organizer']}")

    if row["contact"]:
        parts.append(f"<b>Контакт</b>: {row['contact']}")

    if row["link"]:
        parts.append(f"<b>Ссылка</b>: {row['link']}")

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

def format_event_date(row) -> str:
    if row["date_text"]:
        return row["date_text"]

    date_start = row["date_start"]
    date_end = row["date_end"]
    precision = row["date_precision"]

    if precision == "none":
        return "Дата уточняется"

    if date_start and date_end:
        if date_start.year == date_end.year and date_start.month == date_end.month:
            return f"{date_start.strftime('%d')}-{date_end.strftime('%d.%m.%Y')}"
        return f"{date_start.strftime('%d.%m.%Y')} - {date_end.strftime('%d.%m.%Y')}"

    if date_start and precision == "month":
        return date_start.strftime("%m.%Y")

    if date_start:
        return date_start.strftime("%d.%m.%Y")

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
        return f"{time_start.strftime('%H:%M')}-{time_end.strftime('%H:%M')}"

    if time_start:
        return time_start.strftime("%H:%M")

    return ""


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
    pages = await get_section_pages(db_pool, section_code)

    title = SECTION_TITLES.get(section_code, "Раздел")

    if not pages:
        await message.answer(
            f"{title}\n\nРаздел пока пуст.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    await message.answer(
        f"{title}\n\nВыберите раздел:",
        reply_markup=build_section_menu_keyboard(section_code, pages),
    )


async def edit_section_menu(callback: CallbackQuery, db_pool, section_code: str):
    pages = await get_section_pages(db_pool, section_code)

    title = SECTION_TITLES.get(section_code, "Раздел")

    if not pages:
        await callback.message.edit_text(
            f"{title}\n\nРаздел пока пуст.",
            reply_markup=build_info_back_keyboard(),
        )
        return

    await callback.message.edit_text(
        f"{title}\n\nВыберите раздел:",
        reply_markup=build_section_menu_keyboard(section_code, pages),
    )


async def show_page(callback: CallbackQuery, db_pool, section_code: str, page_id: str):
    page = await get_page_by_id(db_pool, section_code, page_id)

    if not page:
        await callback.answer("Страница не найдена", show_alert=True)
        return

    parts = []

    if page["title"]:
        parts.append(f"<b>{page['title']}</b>")

    if page["body_html"]:
        parts.append(normalize_html_text(page["body_html"]))

    text = "\n\n".join(parts).strip() or "Без содержимого."

    await callback.message.edit_text(
        text,
        reply_markup=build_page_keyboard(section_code),
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
            "🏐 <b>Расписание залов</b>\n\nРаздел пока пуст.",
            reply_markup=build_info_back_keyboard(),
        )
        return

    parts = ["🏐 <b>Расписание залов</b>"]
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


@router.message(F.text == "📅 Мероприятия")
async def menu_events(message: Message, db_pool):
    rows = await get_active_events(db_pool)

    if not rows:
        await message.answer(
            "📅 <b>Мероприятия</b>\n\nПока нет активных мероприятий.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    await message.answer(
        "📅 <b>Мероприятия</b>\n\nАктуальные события:",
        reply_markup=get_main_menu_keyboard(),
    )

    for row in rows:
        await message.answer(
            build_event_text(row),
            reply_markup=get_main_menu_keyboard(),
        )