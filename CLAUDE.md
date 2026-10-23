# ML-AGENT

Торговый ассистент для Trading Department FITO VITA SRL. Два способа работы с одной
и той же логикой:

1. **Claude Code локально** — три skill'а в `.claude/skills/`, запускаются прямо из
   этого репозитория.
2. **Telegram-бот в облаке** (`bot/`) — тот же функционал 24/7 без открытого
   терминала, через Anthropic API напрямую (без Claude Code SDK).

## Три skill'а (конвейер)

- [`buyer-finder`](.claude/skills/buyer-finder/SKILL.md) — ищет покупателей под
  продукт/услугу, собирает карточки компаний в `output/buyers.xlsx`.
- [`offer-drafter`](.claude/skills/offer-drafter/SKILL.md) — превращает
  `buyers.xlsx` в черновики Gmail (Soft Commercial Offer, нумерация КП, подпись).
  **В v1 только драфты, реальная отправка не делается.**
- [`market-supervisor`](.claude/skills/market-supervisor/SKILL.md) — надзор: QC
  данных и писем, рыночное ресерч, содержание КП, координация первых двух.

Все три читают свой `rules.md`/`SKILL.md` целиком при каждом запуске — это живые
документы, пользователь может менять правила без предупреждения в чате. При
конфликте `rules.md` конкретного skill'а важнее его же `SKILL.md`.

## Бот (`bot/`)

- `app/main.py` — long-polling Telegram-бот, доступ по белому списку
  `ALLOWED_TELEGRAM_USER_IDS` (у бота есть доступ к Gmail и коммерческим данным,
  открывать всем нельзя).
- `app/claude_agent.py` — агентный цикл с tool-use, читает те же файлы skill'ов из
  `SKILLS_DIR`, хранит переписку в `DATA_DIR/conversations/<chat_id>.json`.
- `app/tools/` — `filesystem.py` (чтение skill'ов/скриптов), `gmail.py` (черновики),
  `scripts.py` (запуск скриптов skill'ов, например `build_buyers_xlsx.py`).
- Секреты только через переменные окружения (`config.py`, `.env.example`) — никогда
  в коде/репозитории. Деплой и настройка — см. [bot/README.md](bot/README.md).

## Правила безопасности, важные при любых изменениях

- Не создавай облачные аккаунты и не вводи реальные секреты за пользователя — он
  делает это сам, в своём браузере.
- `buyers.xlsx`, `kp_state.json` и прочие бизнес-данные живут вне репозитория
  (volume на хостинге или локальная `output/`), не коммитить.
- Отправка писем — вручную пользователем; автоматическую отправку не включать без
  явного запроса и явного изменения правил skill'а.
