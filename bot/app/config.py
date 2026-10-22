"""
Централизованное чтение конфигурации из переменных окружения.

Все секреты (токены, ключи) приходят ТОЛЬКО из окружения — их задаёт сам
пользователь через панель своего облачного хостинга. В коде/репозитории
никаких реальных значений нет (см. .env.example).
"""
from __future__ import annotations

import os


def _split_ids(raw: str) -> set[int]:
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            pass
    return ids


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_TELEGRAM_USER_IDS = _split_ids(os.environ.get("ALLOWED_TELEGRAM_USER_IDS", ""))

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN", "")
GMAIL_SENDER_ADDRESS = os.environ.get("GMAIL_SENDER_ADDRESS", "")

DATA_DIR = os.environ.get("DATA_DIR", "/data")
SKILLS_DIR = os.environ.get("SKILLS_DIR", "/app/skills")

GMAIL_CONFIGURED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN)


def validate_startup() -> list[str]:
    """Возвращает список проблем конфигурации, из-за которых бот не должен стартовать."""
    problems = []
    if not TELEGRAM_BOT_TOKEN:
        problems.append("TELEGRAM_BOT_TOKEN не задан")
    if not ALLOWED_TELEGRAM_USER_IDS:
        problems.append(
            "ALLOWED_TELEGRAM_USER_IDS не задан — без белого списка бот с доступом "
            "к коммерческим данным и Gmail был бы открыт любому в Telegram"
        )
    if not ANTHROPIC_API_KEY:
        problems.append("ANTHROPIC_API_KEY не задан")
    return problems
