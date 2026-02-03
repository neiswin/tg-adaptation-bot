# TG Adaptation Bot

Telegram-бот для адаптации молодых работников: справка по мероприятиям, путеводителю и внутренним ресурсам.  
Контент редактируется через Google Sheets, состояние пользователей и статистика — в PostgreSQL.

## Возможности
- Главное меню: мероприятия, путеводитель, FAQ, информация о боте
- Мероприятия из Google Sheets (CSV), форматирование, отключение web-preview
- Пагинация мероприятий по 5 штук (inline-кнопки)
- Учёт пользователей (/start), статистика (/stats для админов)
- (Опционально) /anons — рассылка анонсов администраторами (черновики, превью, рассылка, метрики)

## Технологии
- Python 3.10+
- aiogram (v3)
- PostgreSQL (Docker)
- systemd service (24/7)
- Google Sheets → CSV (публичная публикация листа)

## Быстрый старт (локально)
1) Клонировать репозиторий
2) Создать `.env` по примеру:
```env
BOT_TOKEN=...
ADMIN_IDS=123456789,987654321

SHEET_EVENTS_CSV=...
CONTENT_REFRESH_SEC=300

## optional
ANONS_RATE_DELAY=0.1
Установить зависимости:

python -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
Запустить:

python -m bot.main
Запуск на сервере (VPS)
PostgreSQL поднимается через docker compose

Бот запускается через systemd unit

Пример:

sudo systemctl status tg-adaptation-bot
sudo journalctl -u tg-adaptation-bot -n 100 --no-pager
Структура проекта
bot/main.py — точка входа, handlers/routers

bot/db.py — подключение к PostgreSQL, учёт пользователей

bot/content_events.py — загрузка и форматирование мероприятий (Google Sheets CSV)

bot/anons_handlers.py — (опционально) сценарий анонсов и история

Безопасность
.env не хранится в репозитории

токены и ID админов задаются через переменные окружения

## 3) Добавь файл с примером окружения

Создай `.env.example`:
```bash
nano .env.example
BOT_TOKEN=PUT_YOUR_TOKEN_HERE
ADMIN_IDS=123456789

SHEET_EVENTS_CSV=PASTE_PUBLIC_CSV_URL
CONTENT_REFRESH_SEC=300

ANONS_RATE_DELAY=0.1
