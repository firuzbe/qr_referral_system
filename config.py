import os

# Настройки Telegram бота
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '7852718537:AAGTPfDPxBpxPD7drDQTI-FflH4CYHTnXcY')
ADMIN_ID = 5321942267  # Ваш Telegram ID

# Настройки PostgreSQL
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': os.environ.get('DB_PORT', '5432'),
    'database': os.environ.get('DB_NAME', 'referral_bot'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', 'mirzoev1217')
}

# Настройки бонусов
REFERRAL_BONUS_AMOUNT = 100
REFERRAL_DISCOUNT_PERCENT = 10