import logging
from telegram.ext import Application
from config import TELEGRAM_BOT_TOKEN
from handlers import BotHandlers
from database import db_manager

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    if TELEGRAM_BOT_TOKEN == 'your-telegram-bot-token':
        logger.error("TELEGRAM_BOT_TOKEN not set in environment variables")
        return

    try:
        # Инициализируем базу данных
        logger.info("Initializing database...")
        db_manager.init_database()
        logger.info("Database initialized successfully")

        # Создаем приложение и передаем ему токен
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        # Создаем экземпляр обработчиков и настраиваем их
        bot_handlers = BotHandlers(application)
        bot_handlers.setup_handlers()

        # Запускаем бота
        logger.info("Starting Telegram bot...")
        application.run_polling(drop_pending_updates=True)

    except Exception as e:
        logger.error(f"Failed to start bot: {e}")


if __name__ == '__main__':
    main()