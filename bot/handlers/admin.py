from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import settings
from bot.services.content_sync import sync_all_content

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


@router.message(Command("reload_content"))
async def reload_content_cmd(message: Message, db_pool):
    user_id = message.from_user.id if message.from_user else 0

    if not is_admin(user_id):
        await message.answer("У вас нет доступа к этой команде.")
        return

    status_message = await message.answer("🔄 Обновляю контент...")

    try:
        await sync_all_content(db_pool)
    except Exception as e:
        await status_message.edit_text(
            f"❌ Ошибка при обновлении контента:\n<code>{str(e)}</code>"
        )
        return

    await status_message.edit_text("✅ Контент успешно обновлён.")