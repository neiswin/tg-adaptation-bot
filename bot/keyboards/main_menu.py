from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Мероприятия")],
            [KeyboardButton(text="📘 Полезная информация")],
            [KeyboardButton(text="👥 Молодёжный совет")],
            [KeyboardButton(text="📞 Контакты")],
            [KeyboardButton(text="🤖 О боте")],
        ],
        resize_keyboard=True,
    )