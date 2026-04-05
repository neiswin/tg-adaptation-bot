import asyncpg

from bot.config import settings


async def create_db_pool():
    return await asyncpg.create_pool(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        min_size=1,
        max_size=5,
    )


async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
                last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
                onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE,
                onboarding_completed_at TIMESTAMPTZ
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS welcome_slides (
                id BIGSERIAL PRIMARY KEY,
                slide_id TEXT NOT NULL UNIQUE,
                order_no INT NOT NULL DEFAULT 0,
                title TEXT NOT NULL DEFAULT '',
                body_html TEXT NOT NULL DEFAULT '',
                button_text TEXT,
                button_url TEXT,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_welcome_slides_active_order
            ON welcome_slides (active, order_no);
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS content_pages (
                id BIGSERIAL PRIMARY KEY,
                page_id TEXT NOT NULL UNIQUE,
                section_code TEXT NOT NULL,
                parent_code TEXT,
                menu_title TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                body_html TEXT NOT NULL DEFAULT '',
                button_text TEXT,
                button_url TEXT,
                sort_order INT NOT NULL DEFAULT 0,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_content_pages_section_active_sort
            ON content_pages (section_code, active, sort_order);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_content_pages_parent_code
            ON content_pages (parent_code);
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id BIGSERIAL PRIMARY KEY,
                contact_id TEXT NOT NULL UNIQUE,
                group_code TEXT NOT NULL DEFAULT '',
                department TEXT NOT NULL DEFAULT '',
                person_name TEXT NOT NULL DEFAULT '',
                position TEXT NOT NULL DEFAULT '',
                phone TEXT,
                email TEXT,
                telegram TEXT,
                address TEXT,
                work_hours TEXT,
                note TEXT,
                sort_order INT NOT NULL DEFAULT 0,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_contacts_group_active_sort
            ON contacts (group_code, active, sort_order);
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS faq_items (
                id BIGSERIAL PRIMARY KEY,
                faq_id TEXT NOT NULL UNIQUE,
                category_code TEXT NOT NULL DEFAULT '',
                question TEXT NOT NULL DEFAULT '',
                answer_html TEXT NOT NULL DEFAULT '',
                sort_order INT NOT NULL DEFAULT 0,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_faq_items_category_active_sort
            ON faq_items (category_code, active, sort_order);
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hall_schedule (
                id BIGSERIAL PRIMARY KEY,
                slot_id TEXT NOT NULL UNIQUE,
                hall_name TEXT NOT NULL DEFAULT '',
                day_of_week INT NOT NULL,
                time_from TIME NOT NULL,
                time_to TIME NOT NULL,
                activity TEXT NOT NULL DEFAULT '',
                note TEXT,
                sort_order INT NOT NULL DEFAULT 0,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id BIGSERIAL PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE,

                title TEXT NOT NULL DEFAULT '',

                date_start DATE,
                date_end DATE,
                time_start TIME,
                time_end TIME,

                date_precision TEXT NOT NULL DEFAULT 'day',
                time_precision TEXT NOT NULL DEFAULT 'none',

                date_text TEXT,
                time_text TEXT,
                sort_date DATE,

                place TEXT,
                description TEXT,
                organizer TEXT,
                contact TEXT,
                link TEXT,

                active BOOLEAN NOT NULL DEFAULT TRUE,
                sort_order INT NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_active_sort
            ON events (active, sort_date, sort_order);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_date_start
            ON events (date_start);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_event_id
            ON events (event_id);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_hall_schedule_hall_day_active_sort
            ON hall_schedule (hall_name, day_of_week, active, sort_order);
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS content_sync_state (
                source_name TEXT PRIMARY KEY,
                last_sync_at TIMESTAMPTZ,
                last_success_at TIMESTAMPTZ,
                last_status TEXT NOT NULL DEFAULT 'never',
                row_count INT NOT NULL DEFAULT 0,
                error_text TEXT
            );
        """)
        
        await conn.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN NOT NULL DEFAULT FALSE;
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id BIGSERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_by BIGINT NOT NULL,
                text_html TEXT NOT NULL DEFAULT '',
                photo_file_id TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                posted_at TIMESTAMPTZ,
                preview_chat_id BIGINT,
                preview_message_id BIGINT,
                sent_job_started_at TIMESTAMPTZ,
                sent_job_finished_at TIMESTAMPTZ
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS announcement_stats (
                announcement_id BIGINT PRIMARY KEY REFERENCES announcements(id) ON DELETE CASCADE,
                total_target INT NOT NULL DEFAULT 0,
                sent_ok INT NOT NULL DEFAULT 0,
                sent_fail INT NOT NULL DEFAULT 0,
                blocked_count INT NOT NULL DEFAULT 0
            );
        """)

async def upsert_user(
    pool,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (
                telegram_id, username, first_name, last_name, first_seen, last_seen
            )
            VALUES ($1, $2, $3, $4, now(), now())
            ON CONFLICT (telegram_id)
            DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                last_seen = now()
        """, telegram_id, username, first_name, last_name)


async def get_user(pool, telegram_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT
                telegram_id,
                username,
                first_name,
                last_name,
                first_seen,
                last_seen,
                onboarding_completed,
                onboarding_completed_at
            FROM users
            WHERE telegram_id = $1
        """, telegram_id)


async def set_onboarding_completed(pool, telegram_id: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE users
            SET onboarding_completed = TRUE,
                onboarding_completed_at = now()
            WHERE telegram_id = $1
        """, telegram_id)        