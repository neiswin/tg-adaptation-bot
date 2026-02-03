import csv
import html
import io
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import aiohttp

@dataclass
class Event:
    date: datetime
    time_str: str
    title: str
    place: str
    description: str
    organizer: str
    contact: str
    link: str
    active: bool

_cache: List[Event] = []
_cache_ts: float = 0.0

def _parse_date(date_str: str, time_str: str) -> datetime:
    date_str = (date_str or "").strip()
    time_str = (time_str or "").strip() or "00:00"

    # поддержим оба формата: YYYY-MM-DD и DD.MM.YYYY
    for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(f"{date_str} {time_str}", fmt)
        except ValueError:
            pass
    raise ValueError(f"Bad date/time: {date_str} {time_str}")

def _to_bool(v: str) -> bool:
    return str(v).strip() == "1"

async def load_events(force: bool = False) -> List[Event]:
    global _cache, _cache_ts

    url = os.getenv("SHEET_EVENTS_CSV", "").strip()
    if not url:
        return []

    refresh_sec = int(os.getenv("CONTENT_REFRESH_SEC", "300") or "300")
    now_ts = datetime.utcnow().timestamp()
    if (not force) and _cache and (now_ts - _cache_ts) < refresh_sec:
        return _cache

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=20) as resp:
            resp.raise_for_status()
            text = await resp.text()

    reader = csv.DictReader(io.StringIO(text))
    events: List[Event] = []

    for row in reader:
        if not _to_bool(row.get("active", "0")):
            continue

        date_raw = row.get("date", "")
        time_raw = row.get("time", "")
        try:
            dt = _parse_date(date_raw, time_raw)
        except ValueError:
            # пропускаем битые строки вместо падения бота
            continue

        e = Event(
            date=dt,
            time_str=(time_raw or "").strip(),
            title=(row.get("title", "") or "").strip(),
            place=(row.get("place", "") or "").strip(),
            description=(row.get("description", "") or "").strip(),
            organizer=(row.get("organizer", "") or "").strip(),
            contact=(row.get("contact", "") or "").replace("\n", " ").strip(),
            link=(row.get("link", "") or "").strip(),
            active=True,
        )
        events.append(e)

    events.sort(key=lambda x: x.date)
    _cache = events
    _cache_ts = now_ts
    return _cache


def format_events_page(events: List[Event], offset: int = 0, limit: int = 5) -> tuple[str, int, int]:
    """
    Возвращает: (text, total, shown)
    offset — с какого элемента начинать
    """
    now = datetime.now()
    upcoming = [e for e in events if e.date >= now]
    total = len(upcoming)

    page = upcoming[offset: offset + limit]
    if not page:
        return "Ближайших мероприятий пока нет.", total, 0

    lines = [f"🗓 <b>Мероприятия</b> <i>({offset+1}-{min(offset+limit, total)} из {total})</i>"]
    for e in page:
        d = e.date.strftime("%d.%m.%Y")

        title = html.escape(e.title or "")
        place = html.escape(e.place or "")
        organizer = html.escape(e.organizer or "")
        contact = html.escape(e.contact or "")
        link = html.escape(e.link or "")

        if e.time_str:
            lines.append(f"\n• <b>{d} {html.escape(e.time_str)}</b> — <b>{title}</b>")
        else:
            lines.append(f"\n• <b>{d}</b> — <b>{title}</b>")

        if place:
            lines.append(f"  📍 <b>Место:</b> {place}")

        if e.description:
            desc = " ".join(e.description.split())
            if len(desc) > 300:
                desc = desc[:297] + "..."
            lines.append(f"  📝 <b>Описание:</b> {html.escape(desc)}")

        if organizer:
            lines.append(f"  👥 <b>Организатор:</b> {organizer}")
        if contact:
            lines.append(f"  ☎️ <b>Контакт:</b> {contact}")
        if link:
            lines.append(f"  🔗 <b>Ссылка:</b> {link}")

    return "\n".join(lines), total, len(page)


def format_upcoming(events: List[Event], limit: int = 5) -> str:
    now = datetime.now()
    upcoming = [e for e in events if e.date >= now][:limit]
    if not upcoming:
        return "Ближайших мероприятий пока нет."

    lines = ["🗓 <b>Ближайшие мероприятия:</b>"]
    for e in upcoming:
        d = e.date.strftime("%d.%m.%Y")

        title = html.escape(e.title or "")
        place = html.escape(e.place or "")
        organizer = html.escape(e.organizer or "")
        contact = html.escape(e.contact or "")
        link = html.escape(e.link or "")

        if e.time_str:
            lines.append(f"\n• <b>{d} {html.escape(e.time_str)}</b> — <b>{title}</b>")
        else:
            lines.append(f"\n• <b>{d}</b> — <b>{title}</b>")

        if place:
            lines.append(f"  📍 <b>Место:</b> {place}")

        if e.description:
            desc = " ".join(e.description.split())
            if len(desc) > 300:
                desc = desc[:297] + "..."
            lines.append(f"  📝 <b>Описание:</b> {html.escape(desc)}")

        if organizer:
            lines.append(f"  👥 <b>Организатор:</b> {organizer}")
        if contact:
            lines.append(f"  ☎️ <b>Контакт:</b> {contact}")
        if link:
            lines.append(f"  🔗 <b>Ссылка:</b> {link}")

    return "\n".join(lines)
