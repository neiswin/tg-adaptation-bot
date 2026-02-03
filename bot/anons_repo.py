import asyncpg

class AnonsRepo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create_draft(self, created_by: int) -> int:
        row = await self.pool.fetchrow(
            "INSERT INTO announcements (created_by) VALUES ($1) RETURNING id",
            created_by,
        )
        return int(row["id"])

    async def get(self, ann_id: int):
        return await self.pool.fetchrow("SELECT * FROM announcements WHERE id=$1", ann_id)

    async def update_text(self, ann_id: int, text_html: str):
        await self.pool.execute(
            "UPDATE announcements SET text_html=$2 WHERE id=$1",
            ann_id, text_html
        )

    async def update_photo(self, ann_id: int, file_id: str | None):
        await self.pool.execute(
            "UPDATE announcements SET photo_file_id=$2 WHERE id=$1",
            ann_id, file_id
        )

    async def update_button(self, ann_id: int, button_text: str | None, button_url: str | None):
        await self.pool.execute(
            "UPDATE announcements SET button_text=$2, button_url=$3 WHERE id=$1",
            ann_id, button_text, button_url
        )

    async def set_preview_message(self, ann_id: int, chat_id: int, message_id: int):
        await self.pool.execute(
            "UPDATE announcements SET preview_chat_id=$2, preview_message_id=$3 WHERE id=$1",
            ann_id, chat_id, message_id
        )

    async def cancel(self, ann_id: int):
        await self.pool.execute(
            "UPDATE announcements SET status='canceled' WHERE id=$1 AND status='draft'",
            ann_id
        )

    async def try_mark_sending(self, ann_id: int) -> bool:
        # идемпотентность: одним апдейтом “захватываем” рассылку
        row = await self.pool.fetchrow(
            """
            UPDATE announcements
            SET sent_job_started_at=now()
            WHERE id=$1
              AND status='draft'
              AND sent_job_started_at IS NULL
            RETURNING id
            """,
            ann_id
        )
        return row is not None

    async def mark_posted(self, ann_id: int):
        await self.pool.execute(
            """
            UPDATE announcements
            SET status='posted', posted_at=now(), sent_job_finished_at=now()
            WHERE id=$1
            """,
            ann_id
        )

    async def save_stats(self, ann_id: int, total: int, ok: int, fail: int, blocked: int):
        await self.pool.execute(
            """
            INSERT INTO announcement_stats(announcement_id, total_target, sent_ok, sent_fail, blocked_count)
            VALUES($1,$2,$3,$4,$5)
            ON CONFLICT (announcement_id) DO UPDATE
              SET total_target=EXCLUDED.total_target,
                  sent_ok=EXCLUDED.sent_ok,
                  sent_fail=EXCLUDED.sent_fail,
                  blocked_count=EXCLUDED.blocked_count
            """,
            ann_id, total, ok, fail, blocked
        )

    async def list_posted(self, offset: int, limit: int = 10):
        return await self.pool.fetch(
            """
            SELECT id, created_at, posted_at, text_html
            FROM announcements
            WHERE status='posted'
            ORDER BY posted_at DESC NULLS LAST, created_at DESC
            OFFSET $1 LIMIT $2
            """,
            offset, limit
        )

    async def copy_as_new_draft(self, ann_id: int, created_by: int) -> int:
        row = await self.pool.fetchrow(
            """
            INSERT INTO announcements (created_by, text_html, photo_file_id, button_text, button_url, status)
            SELECT $2, text_html, photo_file_id, button_text, button_url, 'draft'
            FROM announcements WHERE id=$1
            RETURNING id
            """,
            ann_id, created_by
        )
        return int(row["id"])

    async def add_click(self, ann_id: int, telegram_id: int):
        await self.pool.execute(
            "INSERT INTO announcement_clicks(announcement_id, telegram_id) VALUES($1,$2)",
            ann_id, telegram_id
        )

    async def get_clicks_count(self, ann_id: int) -> int:
        row = await self.pool.fetchrow(
            "SELECT count(*)::int AS c FROM announcement_clicks WHERE announcement_id=$1",
            ann_id
        )
        return int(row["c"] or 0)

    async def get_stats(self, ann_id: int):
        return await self.pool.fetchrow(
            "SELECT * FROM /announcement_stats WHERE announcement_id=$1",
            ann_id
        )
