"""
Агентный цикл Claude с tool-use — замена тому, что раньше делал Claude Code
локально (чтение skill'ов, запуск скриптов, работа с Gmail), но как отдельный
постоянно работающий облачный процесс, которым управляют из Telegram.

Переписка по каждому чату хранится в DATA_DIR/conversations/<chat_id>.json,
чтобы не терять контекст при перезапуске контейнера (редеплой на хостинге).
"""
import json
import logging
import os

from anthropic import Anthropic, BadRequestError

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, DATA_DIR, SKILLS_DIR
from app.tools import filesystem, gmail, scripts

logger = logging.getLogger(__name__)

client = Anthropic(api_key=ANTHROPIC_API_KEY)

MAX_TOOL_ROUNDS = 12
MAX_HISTORY_MESSAGES = 40  # обрезаем старую историю, чтобы не раздувать контекст/счёт

SYSTEM_PROMPT = """\
Ты — торговый ассистент Trading Department FITO VITA SRL в Telegram. Ты заменяешь
агента, который раньше работал внутри Claude Code с тремя skill'ами. Эти skill'ы
физически лежат как файлы в /app/skills (инструмент list_skill_tree/read_skill_file) —
они НЕ в этом системном промпте, читай их сам по необходимости, как и раньше.

Три направления работы (подробности — в SKILL.md каждого):
1. buyer-finder (skills/buyer-finder) — поиск покупателей под продукт, сбор в
   buyers.xlsx/buyers.json в рабочей директории.
2. offer-drafter (skills/offer-drafter) — подготовка Soft Commercial Offer и
   черновиков Gmail по найденным покупателям. ОБЯЗАТЕЛЬНО прочитай
   skills/offer-drafter/rules.md целиком перед тем как делать что-либо в этом
   направлении — это живой документ с обязательными правилами (нумерация КП,
   подпись, отсутствие вложений по умолчанию, строго последовательное
   создание драфтов в обратном порядке, немедленная остановка при ошибке).
3. market-supervisor (skills/market-supervisor) — контроль качества данных о
   покупателях и писем, владение содержанием КП по продуктам. Прочитай
   skills/market-supervisor/rules.md перед работой в этом направлении.

Рабочие файлы (buyers.xlsx, kp_state.json, вложения, заметки) живут в рабочей
директории (инструменты list_data_tree/read_data_file/write_data_file/
read_xlsx_sheet) — НЕ в skills/, туда только читай инструкции.

Готовые python-скрипты из skill'ов запускай через run_script (см.
list_available_scripts) вместо того чтобы писать свою логику заново —
kp_number.py выдаёт номера КП, record_draft.py и append_row.py пишут в
buyers.xlsx, build_buyers_xlsx.py строит buyers.xlsx из buyers.json.

Gmail-черновики — через gmail_create_draft/gmail_list_drafts/gmail_get_draft/
gmail_update_draft/gmail_delete_draft. Если они возвращают ошибку "Gmail не
настроен" — сообщи об этом пользователю прямо, не изображай, что письмо создано.

Общение — на русском, по-деловому, без лишней воды. Если правила skill'а и
прямая просьба пользователя в этом чате противоречат друг другу — следуй
правилам, но явно скажи пользователю, в чём противоречие, и спроси, как быть
(не нарушай правила тихо). Если чего-то не хватает (нет email покупателя, не
настроен Gmail, файл не найден) — остановись и спроси, не выдумывай данные.
"""

TOOLS = [
    {
        "name": "list_skill_tree",
        "description": "Список файлов внутри указанного skill'а (или всех, если sub_path пуст).",
        "input_schema": {
            "type": "object",
            "properties": {"sub_path": {"type": "string", "description": "Например 'offer-drafter'"}},
        },
    },
    {
        "name": "read_skill_file",
        "description": "Читает текстовый файл skill'а целиком (SKILL.md, rules.md, шаблон, .py скрипт).",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "list_data_tree",
        "description": "Список файлов в рабочей директории (buyers.xlsx, kp_state.json, вложения и т.п.).",
        "input_schema": {
            "type": "object",
            "properties": {"sub_path": {"type": "string"}},
        },
    },
    {
        "name": "read_data_file",
        "description": "Читает текстовый файл (.json/.md/.txt/.csv) из рабочей директории.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_data_file",
        "description": "Создаёт/перезаписывает текстовый файл (.json/.md/.txt) в рабочей директории.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_xlsx_sheet",
        "description": "Читает лист .xlsx из рабочей директории. Без sheet_name — возвращает список листов.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "sheet_name": {"type": "string"},
                "max_rows": {"type": "integer"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_available_scripts",
        "description": "Список разрешённых готовых скриптов, которые можно запускать через run_script.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_script",
        "description": "Запускает один из разрешённых скриптов skill'ов с аргументами командной строки.",
        "input_schema": {
            "type": "object",
            "properties": {
                "script": {"type": "string"},
                "args": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["script"],
        },
    },
    {
        "name": "gmail_create_draft",
        "description": "Создаёт новый черновик письма в Gmail.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "array", "items": {"type": "string"}},
                "subject": {"type": "string"},
                "body_text": {"type": "string"},
                "html_body": {"type": "string"},
                "cc": {"type": "array", "items": {"type": "string"}},
                "bcc": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["to", "subject", "body_text"],
        },
    },
    {
        "name": "gmail_list_drafts",
        "description": "Список черновиков Gmail, опционально по поисковому запросу (синтаксис Gmail search).",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}},
        },
    },
    {
        "name": "gmail_get_draft",
        "description": "Полное содержимое одного черновика по id.",
        "input_schema": {
            "type": "object",
            "properties": {"draft_id": {"type": "string"}},
            "required": ["draft_id"],
        },
    },
    {
        "name": "gmail_update_draft",
        "description": "Полностью заменяет содержимое существующего черновика.",
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string"},
                "to": {"type": "array", "items": {"type": "string"}},
                "subject": {"type": "string"},
                "body_text": {"type": "string"},
                "html_body": {"type": "string"},
                "cc": {"type": "array", "items": {"type": "string"}},
                "bcc": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["draft_id", "to", "subject", "body_text"],
        },
    },
    {
        "name": "gmail_delete_draft",
        "description": "Удаляет черновик по id.",
        "input_schema": {
            "type": "object",
            "properties": {"draft_id": {"type": "string"}},
            "required": ["draft_id"],
        },
    },
]

DISPATCH = {
    "list_skill_tree": lambda **kw: filesystem.list_skill_tree(kw.get("sub_path", "")),
    "read_skill_file": lambda **kw: filesystem.read_skill_file(kw["path"]),
    "list_data_tree": lambda **kw: filesystem.list_data_tree(kw.get("sub_path", "")),
    "read_data_file": lambda **kw: filesystem.read_data_file(kw["path"]),
    "write_data_file": lambda **kw: filesystem.write_data_file(kw["path"], kw["content"]),
    "read_xlsx_sheet": lambda **kw: filesystem.read_xlsx_sheet(
        kw["path"], kw.get("sheet_name"), kw.get("max_rows", 300)
    ),
    "list_available_scripts": lambda **kw: scripts.list_available_scripts(),
    "run_script": lambda **kw: scripts.run_script(kw["script"], kw.get("args", [])),
    "gmail_create_draft": lambda **kw: gmail.create_draft(**kw),
    "gmail_list_drafts": lambda **kw: gmail.list_drafts(**kw),
    "gmail_get_draft": lambda **kw: gmail.get_draft(**kw),
    "gmail_update_draft": lambda **kw: gmail.update_draft(**kw),
    "gmail_delete_draft": lambda **kw: gmail.delete_draft(**kw),
}


def _conv_path(chat_id: int) -> str:
    return os.path.join(DATA_DIR, "conversations", f"{chat_id}.json")


def _load_history(chat_id: int) -> list:
    path = _conv_path(chat_id)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.exception("Не удалось прочитать историю чата %s", chat_id)
    return []


def _save_history(chat_id: int, messages: list) -> None:
    path = _conv_path(chat_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(messages[-MAX_HISTORY_MESSAGES:], f, ensure_ascii=False)


def reset_history(chat_id: int) -> None:
    path = _conv_path(chat_id)
    if os.path.isfile(path):
        os.remove(path)


def _execute_tool(name: str, tool_input: dict) -> dict:
    fn = DISPATCH.get(name)
    if fn is None:
        return {"error": f"Неизвестный инструмент: {name}"}
    try:
        return fn(**tool_input)
    except Exception as exc:  # инструмент не должен обрывать весь цикл
        logger.exception("Ошибка инструмента %s", name)
        return {"error": f"{type(exc).__name__}: {exc}"}


def run_turn(chat_id: int, user_text: str) -> str:
    """Один обмен репликами: добавляет сообщение пользователя, прогоняет цикл
    tool-use до финального текстового ответа, сохраняет историю, возвращает ответ."""
    messages = _load_history(chat_id)
    messages.append({"role": "user", "content": user_text})

    tools = TOOLS
    use_web_search = True
    final_text = ""

    for _ in range(MAX_TOOL_ROUNDS):
        request_tools = tools + (
            [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
            if use_web_search
            else []
        )
        try:
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=request_tools,
                messages=messages,
            )
        except BadRequestError:
            if use_web_search:
                # аккаунт/модель не поддерживает серверный web_search - отключаем и пробуем снова
                use_web_search = False
                continue
            raise

        assistant_content = [block.model_dump() for block in response.content]
        messages.append({"role": "assistant", "content": assistant_content})

        text_parts = [b["text"] for b in assistant_content if b.get("type") == "text"]
        final_text = "\n".join(text_parts) if text_parts else final_text

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in assistant_content:
            if block.get("type") != "tool_use":
                continue
            result = _execute_tool(block["name"], block.get("input", {}))
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": json.dumps(result, ensure_ascii=False),
            })
        messages.append({"role": "user", "content": tool_results})
    else:
        final_text = final_text or (
            "Остановился: слишком много шагов подряд без финального ответа. "
            "Опишите задачу короче или по частям."
        )

    _save_history(chat_id, messages)
    return final_text or "(пустой ответ)"
