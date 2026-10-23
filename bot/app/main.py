"""
Точка входа. Long-polling Telegram-бот (без вебхуков — не нужен публичный
HTTPS-адрес, достаточно исходящего соединения с серверов Telegram, что
упрощает деплой на большинстве облачных хостингов).

Доступ ограничен белым списком Telegram user id (ALLOWED_TELEGRAM_USER_IDS) —
у бота есть доступ к коммерческим данным и к созданию черновиков в Gmail,
поэтому отвечать всем подряд нельзя.

Автономный полный пайплайн (досье продукта -> до 50 покупателей/драфтов за один
прогон, см. market-supervisor/SKILL.md Шаг 7) может идти десятки минут и сотни
вызовов инструментов — поэтому run_turn выполняется в отдельном потоке
(asyncio.to_thread), не блокируя обработку других сообщений, а промежуточные
сообщения прогресса (send_progress_update) долетают до пользователя сразу,
через asyncio.run_coroutine_threadsafe обратно на event loop бота.
"""
import asyncio
import logging
import os
import re
import sys

from telegram import Bot, Update
from telegram.constants import ChatAction
from telegram.ext import Application, ContextTypes, MessageHandler, CommandHandler, filters

from app import claude_agent, config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("bot")

INBOX_DIRNAME = "inbox"
TELEGRAM_CHUNK = 4000  # запас от лимита Telegram в 4096 символов на сообщение


def _is_allowed(user_id: int) -> bool:
    return user_id in config.ALLOWED_TELEGRAM_USER_IDS


def _safe_filename(name: str) -> str:
    name = os.path.basename(name or "file")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "file"
    return name[:120]


async def _send_chunks(bot: Bot, chat_id: int, text: str) -> None:
    text = text or "(пустой ответ)"
    for i in range(0, len(text), TELEGRAM_CHUNK):
        await bot.send_message(chat_id=chat_id, text=text[i : i + TELEGRAM_CHUNK])


def _make_progress_callback(bot: Bot, chat_id: int, loop: asyncio.AbstractEventLoop):
    """Возвращает синхронную функцию, которую claude_agent.run_turn вызывает (из
    рабочего потока) при каждом send_progress_update — она планирует отправку
    сообщения обратно на event loop бота, не дожидаясь завершения всего хода."""

    def on_progress(message: str) -> None:
        future = asyncio.run_coroutine_threadsafe(
            _send_chunks(bot, chat_id, f"⏳ {message}"), loop
        )

        def _log_errors(fut):
            exc = fut.exception()
            if exc:
                logger.exception("Не удалось отправить промежуточное сообщение", exc_info=exc)

        future.add_done_callback(_log_errors)

    return on_progress


async def _run_and_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, user_text: str) -> None:
    chat_id = update.effective_chat.id
    loop = asyncio.get_running_loop()
    on_progress = _make_progress_callback(context.bot, chat_id, loop)

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    try:
        reply = await asyncio.to_thread(claude_agent.run_turn, chat_id, user_text, on_progress)
    except Exception:
        logger.exception("Ошибка при обработке сообщения")
        reply = "Внутренняя ошибка при обработке запроса. Попробуйте ещё раз или /reset."

    await _send_chunks(context.bot, chat_id, reply)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "Готов к работе. Можно писать задачу текстом (например «найди 15 покупателей "
        "для CFA» или «подготовь волну КП») или сразу прислать файлы по новому продукту "
        "(спецификацию/анализ рынка/КП — PDF, DOCX, XLSX или просто текст) и попросить "
        "сделать всё целиком: разбор рынка, поиск покупателей, черновики писем. "
        "/reset — очистить историю разговора."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return
    claude_agent.reset_history(update.effective_chat.id)
    await update.message.reply_text("История разговора очищена.")


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Доступен всем, без проверки белого списка - чтобы владелец узнал свой
    # Telegram user id и мог занести его в ALLOWED_TELEGRAM_USER_IDS.
    await update.message.reply_text(f"Ваш Telegram user id: {update.effective_user.id}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_allowed(user.id):
        logger.warning("Отклонено сообщение от неразрешённого пользователя %s (%s)", user.id, user.username)
        return
    await _run_and_reply(update, context, update.message.text)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Приём файлов (спецификация/анализ рынка/КП) по новому продукту. Скачивает файл
    на постоянный диск в inbox/<chat_id>/ и сообщает модели путь + подпись к файлу,
    чтобы она сама решила, читать его сейчас (read_pdf_file/read_docx_file/
    read_data_file/read_xlsx_sheet) или ждать ещё файлов/команду начинать."""
    user = update.effective_user
    if not _is_allowed(user.id):
        logger.warning("Отклонено сообщение от неразрешённого пользователя %s (%s)", user.id, user.username)
        return

    document = update.message.document
    chat_id = update.effective_chat.id
    safe_name = _safe_filename(document.file_name)
    rel_dir = os.path.join(INBOX_DIRNAME, str(chat_id))
    abs_dir = os.path.join(config.DATA_DIR, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)

    rel_path = os.path.join(rel_dir, safe_name)
    abs_path = os.path.join(config.DATA_DIR, rel_path)
    if os.path.exists(abs_path):
        stem, ext = os.path.splitext(safe_name)
        rel_path = os.path.join(rel_dir, f"{stem}_{document.file_unique_id}{ext}")
        abs_path = os.path.join(config.DATA_DIR, rel_path)

    tg_file = await context.bot.get_file(document.file_id)
    await tg_file.download_to_drive(abs_path)

    caption = (update.message.caption or "").strip()
    size_kb = (document.file_size or 0) / 1024
    note = (
        f"[Системное уведомление: пользователь прислал файл через Telegram. "
        f"Путь в рабочей директории: {rel_path!r}. Инструмент для чтения зависит от "
        f"расширения: read_data_file (.txt/.md/.json/.csv), read_pdf_file (.pdf), "
        f"read_docx_file (.docx), read_xlsx_sheet (.xlsx). "
        f"Исходное имя файла: {document.file_name!r}, ~{size_kb:.0f} КБ, "
        f"mime: {document.mime_type}."
        + (f" Подпись к файлу от пользователя: {caption!r}." if caption else "")
        + "]"
    )
    await _run_and_reply(update, context, note)


def main() -> None:
    problems = config.validate_startup()
    if problems:
        for p in problems:
            logger.error("Конфигурация не готова: %s", p)
        sys.exit(1)

    # concurrent_updates=True - чтобы долгий автономный прогон (Шаг 7, десятки минут) не
    # блокировал обработку других входящих сообщений/команд (например /reset) этого же
    # или другого чата, пока он выполняется в фоновом потоке.
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен, разрешённые user id: %s", config.ALLOWED_TELEGRAM_USER_IDS)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
