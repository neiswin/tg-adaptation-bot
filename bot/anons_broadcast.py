import asyncio
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter

async def broadcast_announcement(
    bot: Bot,
    pool,
    ann_id: int,
    text_html: str,
    photo_file_id: str | None,
    join_callback_data: str | None,
    disable_preview: bool = True,
    rate_delay: float = 0.1,
):
    total = ok = fail = blocked = 0

    rows = await pool.fetch("SELECT telegram_id FROM users WHERE is_blocked=false")
    total = len(rows)

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    kb = None
    if join_callback_data:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Записаться", callback_data=join_callback_data)]
            ]
        )

    for r in rows:
        uid = int(r["telegram_id"])
        try:
            if photo_file_id:
                await bot.send_photo(
                    chat_id=uid,
                    photo=photo_file_id,
                    caption=text_html[:1024],
                    parse_mode="HTML",
                    reply_markup=kb,
                    disable_notification=False,
                )
            else:
                await bot.send_message(
                    chat_id=uid,
                    text=text_html,
                    parse_mode="HTML",
                    reply_markup=kb,
                    disable_web_page_preview=disable_preview,
                )
            ok += 1

        except TelegramRetryAfter as e:
            await asyncio.sleep(float(e.retry_after) + 0.5)
            fail += 1

        except TelegramForbiddenError:
            # blocked by user
            blocked += 1
            await pool.execute("UPDATE users SET is_blocked=true WHERE telegram_id=$1", uid)

        except TelegramBadRequest as e:
            # chat not found, etc.
            msg = str(e)
            if "chat not found" in msg.lower():
                blocked += 1
                await pool.execute("UPDATE users SET is_blocked=true WHERE telegram_id=$1", uid)
            else:
                fail += 1

        except Exception:
            fail += 1

        await asyncio.sleep(rate_delay)

    return total, ok, fail, blocked
