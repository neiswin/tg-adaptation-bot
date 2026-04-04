from datetime import date, datetime, time

from bot.config import settings
from bot.services.google_sheets import fetch_csv_rows


def as_text(value) -> str:
    return (value or "").strip()


def as_optional_text(value):
    value = as_text(value)
    return value or None


def as_int(value, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def as_bool(value) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "да"}




def as_day_of_week(value) -> int:
    raw = as_text(value).lower()
    mapping = {
        "1": 1, "пн": 1, "понедельник": 1,
        "2": 2, "вт": 2, "вторник": 2,
        "3": 3, "ср": 3, "среда": 3,
        "4": 4, "чт": 4, "четверг": 4,
        "5": 5, "пт": 5, "пятница": 5,
        "6": 6, "сб": 6, "суббота": 6,
        "7": 7, "вс": 7, "воскресенье": 7,
    }
    return mapping.get(raw, 1)


def as_time_value(value: str) -> time:
    raw = as_text(value)
    hh, mm = raw.split(":")
    return time(hour=int(hh), minute=int(mm))

def as_optional_time_value(value: str):
    raw = as_text(value)
    if not raw:
        return None

    hh, mm = raw.split(":")
    return time(hour=int(hh), minute=int(mm))

def as_date_value(value: str) -> date:
    raw = as_text(value)

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"Unsupported date format: {raw}")


async def mark_sync_ok(conn, source_name: str, row_count: int):
    await conn.execute("""
        INSERT INTO content_sync_state (
            source_name, last_sync_at, last_success_at, last_status, row_count, error_text
        )
        VALUES ($1, now(), now(), 'ok', $2, NULL)
        ON CONFLICT (source_name)
        DO UPDATE SET
            last_sync_at = now(),
            last_success_at = now(),
            last_status = 'ok',
            row_count = EXCLUDED.row_count,
            error_text = NULL
    """, source_name, row_count)


async def mark_sync_error(conn, source_name: str, error_text: str):
    await conn.execute("""
        INSERT INTO content_sync_state (
            source_name, last_sync_at, last_status, row_count, error_text
        )
        VALUES ($1, now(), 'error', 0, $2)
        ON CONFLICT (source_name)
        DO UPDATE SET
            last_sync_at = now(),
            last_status = 'error',
            error_text = EXCLUDED.error_text
    """, source_name, error_text[:4000])


async def sync_welcome_slides(conn, rows: list[dict]):
    items = []
    for row in rows:
        slide_id = as_text(row.get("slide_id"))
        if not slide_id:
            continue

        items.append({
            "slide_id": slide_id,
            "order_no": as_int(row.get("order_no")),
            "title": as_text(row.get("title")),
            "body_html": as_text(row.get("body_html")),
            "button_text": as_optional_text(row.get("button_text")),
            "button_url": as_optional_text(row.get("button_url")),
            "active": as_bool(row.get("active")),
        })

    async with conn.transaction():
        await conn.execute("DELETE FROM welcome_slides")
        for item in items:
            await conn.execute("""
                INSERT INTO welcome_slides (
                    slide_id, order_no, title, body_html,
                    button_text, button_url, active, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, now())
            """,
            item["slide_id"],
            item["order_no"],
            item["title"],
            item["body_html"],
            item["button_text"],
            item["button_url"],
            item["active"])


async def sync_content_pages(conn, rows: list[dict]):
    items = []
    for row in rows:
        page_id = as_text(row.get("page_id"))
        if not page_id:
            continue

        items.append({
            "page_id": page_id,
            "section_code": as_text(row.get("section_code")),
            "parent_code": as_optional_text(row.get("parent_code")),
            "menu_title": as_text(row.get("menu_title")),
            "title": as_text(row.get("title")),
            "body_html": as_text(row.get("body_html")),
            "button_text": as_optional_text(row.get("button_text")),
            "button_url": as_optional_text(row.get("button_url")),
            "sort_order": as_int(row.get("sort_order")),
            "active": as_bool(row.get("active")),
        })

    async with conn.transaction():
        await conn.execute("DELETE FROM content_pages")
        for item in items:
            await conn.execute("""
                INSERT INTO content_pages (
                    page_id, section_code, parent_code, menu_title, title,
                    body_html, button_text, button_url, sort_order, active, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now())
            """,
            item["page_id"],
            item["section_code"],
            item["parent_code"],
            item["menu_title"],
            item["title"],
            item["body_html"],
            item["button_text"],
            item["button_url"],
            item["sort_order"],
            item["active"])


async def sync_contacts(conn, rows: list[dict]):
    items = []
    for row in rows:
        contact_id = as_text(row.get("contact_id"))
        if not contact_id:
            continue

        items.append({
            "contact_id": contact_id,
            "group_code": as_text(row.get("group_code")),
            "department": as_text(row.get("department")),
            "person_name": as_text(row.get("person_name")),
            "position": as_text(row.get("position")),
            "phone": as_optional_text(row.get("phone")),
            "email": as_optional_text(row.get("email")),
            "telegram": as_optional_text(row.get("telegram")),
            "address": as_optional_text(row.get("address")),
            "work_hours": as_optional_text(row.get("work_hours")),
            "note": as_optional_text(row.get("note")),
            "sort_order": as_int(row.get("sort_order")),
            "active": as_bool(row.get("active")),
        })

    async with conn.transaction():
        await conn.execute("DELETE FROM contacts")
        for item in items:
            await conn.execute("""
                INSERT INTO contacts (
                    contact_id, group_code, department, person_name, position,
                    phone, email, telegram, address, work_hours, note,
                    sort_order, active, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, now())
            """,
            item["contact_id"],
            item["group_code"],
            item["department"],
            item["person_name"],
            item["position"],
            item["phone"],
            item["email"],
            item["telegram"],
            item["address"],
            item["work_hours"],
            item["note"],
            item["sort_order"],
            item["active"])


async def sync_faq_items(conn, rows: list[dict]):
    items = []
    for row in rows:
        faq_id = as_text(row.get("faq_id"))
        if not faq_id:
            continue

        items.append({
            "faq_id": faq_id,
            "category_code": as_text(row.get("category_code")),
            "question": as_text(row.get("question")),
            "answer_html": as_text(row.get("answer_html")),
            "sort_order": as_int(row.get("sort_order")),
            "active": as_bool(row.get("active")),
        })

    async with conn.transaction():
        await conn.execute("DELETE FROM faq_items")
        for item in items:
            await conn.execute("""
                INSERT INTO faq_items (
                    faq_id, category_code, question, answer_html,
                    sort_order, active, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, now())
            """,
            item["faq_id"],
            item["category_code"],
            item["question"],
            item["answer_html"],
            item["sort_order"],
            item["active"])


async def sync_hall_schedule(conn, rows: list[dict]):
    items = []
    for row in rows:
        slot_id = as_text(row.get("slot_id"))
        if not slot_id:
            continue

        items.append({
            "slot_id": slot_id,
            "hall_name": as_text(row.get("hall_name")),
            "day_of_week": as_day_of_week(row.get("day_of_week")),
            "time_from": as_time_value(row.get("time_from")),
            "time_to": as_time_value(row.get("time_to")),
            "activity": as_text(row.get("activity")),
            "note": as_optional_text(row.get("note")),
            "sort_order": as_int(row.get("sort_order")),
            "active": as_bool(row.get("active")),
        })

    async with conn.transaction():
        await conn.execute("DELETE FROM hall_schedule")
        for item in items:
            await conn.execute("""
                INSERT INTO hall_schedule (
                    slot_id, hall_name, day_of_week, time_from, time_to,
                    activity, note, sort_order, active, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
            """,
            item["slot_id"],
            item["hall_name"],
            item["day_of_week"],
            item["time_from"],
            item["time_to"],
            item["activity"],
            item["note"],
            item["sort_order"],
            item["active"])

async def sync_events(conn, rows: list[dict]):
    items = []
    for row in rows:
        event_id = as_text(row.get("event_id"))
        if not event_id:
            continue

        items.append({
            "event_id": event_id,
            "event_date": as_date_value(row.get("event_date")),
            "event_time": as_optional_time_value(row.get("event_time")),
            "title": as_text(row.get("title")),
            "place": as_optional_text(row.get("place")),
            "description": as_optional_text(row.get("description")),
            "organizer": as_optional_text(row.get("organizer")),
            "contact": as_optional_text(row.get("contact")),
            "link": as_optional_text(row.get("link")),
            "active": as_bool(row.get("active")),
        })

    async with conn.transaction():
        await conn.execute("DELETE FROM events")
        for item in items:
            await conn.execute("""
                INSERT INTO events (
                    event_id, event_date, event_time, title, place,
                    description, organizer, contact, link, active, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now())
            """,
            item["event_id"],
            item["event_date"],
            item["event_time"],
            item["title"],
            item["place"],
            item["description"],
            item["organizer"],
            item["contact"],
            item["link"],
            item["active"])

SOURCES = [
    ("welcome_slides", settings.sheet_welcome_csv, sync_welcome_slides),
    ("content_pages", settings.sheet_pages_csv, sync_content_pages),
    ("contacts", settings.sheet_contacts_csv, sync_contacts),
    ("faq_items", settings.sheet_faq_csv, sync_faq_items),
    ("hall_schedule", settings.sheet_halls_csv, sync_hall_schedule),
    ("events", settings.sheet_events_csv, sync_events),
]


async def sync_all_content(pool):
    async with pool.acquire() as conn:
        for source_name, url, sync_func in SOURCES:
            try:
                rows = await fetch_csv_rows(url)
                await sync_func(conn, rows)
                await mark_sync_ok(conn, source_name, len(rows))
                print(f"[content_sync] OK: {source_name}, rows={len(rows)}")
            except Exception as e:
                await mark_sync_error(conn, source_name, str(e))
                print(f"[content_sync] ERROR: {source_name}: {e}")

