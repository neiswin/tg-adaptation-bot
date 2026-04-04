from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


def _get_env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and (value is None or str(value).strip() == ""):
        raise RuntimeError(f"Environment variable {name} is required")
    return value


def _parse_admin_ids(raw: str | None) -> set[int]:
    if not raw:
        return set()

    result = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        result.add(int(item))
    return result


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: set[int]

    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    sheet_welcome_csv: str
    sheet_pages_csv: str
    sheet_contacts_csv: str
    sheet_faq_csv: str
    sheet_halls_csv: str
    sheet_events_csv: str

    content_refresh_sec: int


def load_settings() -> Settings:
    return Settings(
        bot_token=_get_env("BOT_TOKEN", required=True),
        admin_ids=_parse_admin_ids(_get_env("ADMIN_IDS", "")),

        db_host=_get_env("DB_HOST", "127.0.0.1", required=True),
        db_port=int(_get_env("DB_PORT", "5432", required=True)),
        db_name=_get_env("DB_NAME", required=True),
        db_user=_get_env("DB_USER", required=True),
        db_password=_get_env("DB_PASSWORD", required=True),

        sheet_welcome_csv=_get_env("SHEET_WELCOME_CSV", required=True),
        sheet_pages_csv=_get_env("SHEET_PAGES_CSV", required=True),
        sheet_contacts_csv=_get_env("SHEET_CONTACTS_CSV", required=True),
        sheet_faq_csv=_get_env("SHEET_FAQ_CSV", required=True),
        sheet_halls_csv=_get_env("SHEET_HALLS_CSV", required=True),
        sheet_events_csv=_get_env("SHEET_EVENTS_CSV", required=True),

        content_refresh_sec=int(_get_env("CONTENT_REFRESH_SEC", "300")),
    )


settings = load_settings()