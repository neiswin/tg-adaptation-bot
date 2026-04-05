import asyncio
import contextlib

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.db import create_db_pool, init_db
from bot.services.content_sync import sync_all_content
from bot.handlers.start import router as start_router
from bot.handlers.menu import router as menu_router
from bot.handlers.admin import router as admin_router



async def content_sync_loop(pool):
    while True:
        await asyncio.sleep(settings.content_refresh_sec)

        try:
            await sync_all_content(pool)
            print("[background] content synced")
        except Exception as e:
            print(f"[background] content sync failed: {e}")


async def main():
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.include_router(start_router)
    dp.include_router(menu_router)
    dp.include_router(admin_router)

    pool = await create_db_pool()
    await init_db(pool)
    print("[startup] database initialized")

    await sync_all_content(pool)
    print("[startup] content synced")

    sync_task = asyncio.create_task(content_sync_loop(pool))

    dp["db_pool"] = pool

    try:
        print("[startup] start polling")
        await dp.start_polling(bot)
    finally:
        sync_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sync_task

        await bot.session.close()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())