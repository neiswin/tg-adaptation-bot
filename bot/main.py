import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.db import create_db_pool, init_db
from bot.services.content_sync import sync_all_content
from bot.handlers.start import router as start_router
from bot.handlers.menu import router as menu_router


async def main():
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.include_router(start_router)
    dp.include_router(menu_router)

    pool = await create_db_pool()
    await init_db(pool)
    print("[startup] database initialized")
    await sync_all_content(pool)
    print("[startup] content synced")

    dp["db_pool"] = pool

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())