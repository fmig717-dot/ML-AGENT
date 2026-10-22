"""
Точка входа. Long-polling Telegram-бот (без вебхуков — не нужен публичный
HTTPS-адрес, достаточно исходящего соединения с серверов Telegram, что
упрощает деплой на большинстве облачных хостингов).

Доступ ограничен белым списком Telegram user id (ALLOWED_TELEGRAM_USER_IDS) —
у бота есть доступ к коммерческим данным и к созданию черновиков в Gmail,
поэтому отвечать всем подряд нельзя.
"""
import logging
import sys

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, ContextTypes, MessageHandler, CommandHandler, filters

from app import claude_agent, config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("bot")


def _is_allowed(user_id: int) -> bool:
    return user_id in config.ALLOWED_TELEGRAM_USER_IDS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "Готов к работе. Пишите задачу (например: «найди покупателей для CFA» "
        "или «подготовь волну КП»). /reset — очистить историю разговора."
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

    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    try:
        reply = claude_agent.run_turn(chat_id, update.message.text)
    except Exception:
        logger.exception("Ошибка при обработке сообщения")
        reply = "Внутренняя ошибка при обработке запроса. Попробуйте ещё раз или /reset."

    # Telegram ограничивает сообщение 4096 символами - режем на части.
    for i in range(0, len(reply), 4000):
        await update.message.reply_text(reply[i : i + 4000])


def main() -> None:
    problems = config.validate_startup()
    if problems:
        for p in problems:
            logger.error("Конфигурация не готова: %s", p)
        sys.exit(1)

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен, разрешённые user id: %s", config.ALLOWED_TELEGRAM_USER_IDS)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
