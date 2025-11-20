import logging
import re
import qrcode
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

from config import ADMIN_ID
from database import db_manager

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния разговора
START, NAME, EMAIL, PHONE, COMPLETE = range(5)


class BotHandlers:
    def __init__(self, application):
        self.application = application
        self.bot = application.bot

    def generate_qr_code(self, data):
        """Генерация QR-кода"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        bio = BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        return bio

    def generate_referral_link(self, referral_code):
        """Генерация реферальной ссылки"""
        bot_username = self.bot.username
        return f"https://t.me/{bot_username}?start={referral_code}"

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            user = update.effective_user
            telegram_id = user.id

            # Проверяем, передан ли реферальный код в команде start
            referral_code = None
            if context.args and len(context.args) > 0:
                referral_code = context.args[0]

            # Если пользователь уже зарегистрирован
            if db_manager.user_exists(telegram_id):
                if referral_code:
                    # Обрабатываем реферальный код для уже зарегистрированного пользователя
                    await self.process_referral_code(update, context, referral_code, telegram_id)
                else:
                    await update.message.reply_text(
                        f"С возвращением, {user.first_name}! 👋\n\n"
                        "Используйте команды:\n"
                        "/mycode - ваш реферальный код\n"
                        "/myref - ваша реферальная ссылка и QR-код\n"
                        "/balance - ваш баланс бонусов\n"
                        "/referrals - ваши рефералы\n"
                        "/adminpanel - админ панель"
                    )
                return ConversationHandler.END

            # Если у пользователя есть username — регистрируем автоматически (только username)
            if user.username:
                try:
                    # При создании мы передаём username и минимум данных; db_manager должен принять такие значения
                    user_id, user_referral_code = db_manager.create_user(
                        telegram_id=telegram_id,
                        username=user.username,
                        first_name=None,
                        last_name=None,
                        patronymic=None,
                        email=None,
                        phone=None
                    )
                    # Привязываем referral, если был код в параметрах /start
                    if referral_code and user_id:
                        referrer = db_manager.get_user_by_referral_code(referral_code)
                        if referrer and referrer['telegram_id'] != telegram_id:
                            db_manager.create_referral(referrer['id'], user_id, referral_code)

                    await update.message.reply_text(
                        "🎉 Вы успешно зарегистрированы автоматически по username! 🎉\n\n"
                        f"👤 Username: @{user.username}\n\n"
                        "Если хотите добавить email или телефон — используйте /start и пройдите регистрацию вручную, "
                        "или обратитесь к администратору.\n\n"
                        "Доступные команды:\n"
                        "/mycode - ваш реферальный код\n"
                        "/myref - реферальная ссылка и QR-код\n"
                        "/balance - ваш баланс\n"
                        "/referrals - ваши рефералы\n"
                        "/adminpanel - админ панель\n"
                    )
                except Exception as e:
                    logger.error(f"Error auto-register by username: {e}")
                    await update.message.reply_text(
                        "❌ Ошибка при автоматической регистрации. Попробуйте /start ещё раз."
                    )
                return ConversationHandler.END

            # Если username нет — используем сессию и просим ФИО
            if not db_manager.get_user_session(telegram_id):
                db_manager.create_user_session(telegram_id)

            if referral_code:
                db_manager.update_user_session(telegram_id, registration_data={'referral_code': referral_code})

            await update.message.reply_text(
                f"Привет, {user.first_name}! 🎉\n\n"
                "Добро пожаловать в реферальную систему!\n\n"
                "🔹 Регистрируйтесь и получайте персональный реферальный код\n"
                "🔹 Приглашайте друзей и получайте бонусы\n\n"
                "📝 Как вас зовут? (Фамилия Имя Отчество):"
            )
            return NAME
        except Exception as e:
            logger.error(f"Error in start: {e}")
            await update.message.reply_text("❌ Произошла ошибка. Попробуйте еще раз.")
            return ConversationHandler.END

    async def start_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстового 'start' без слеша"""
        return await self.start(update, context)

    async def process_referral_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE, referral_code: str,
                                    telegram_id: int):
        """Обработка реферального кода для существующего пользователя"""
        try:
            referrer = db_manager.get_user_by_referral_code(referral_code)
            if referrer and referrer['telegram_id'] != telegram_id:
                # Создаем реферальную связь
                user = db_manager.get_user_by_telegram_id(telegram_id)
                db_manager.create_referral(referrer['id'], user['id'], referral_code)

                await update.message.reply_text(
                    "✅ Реферальный код успешно применен!\n\n"
                    f"Вы были приглашены пользователем: {referrer.get('username')}\n"
                    "Бонус будет начислен после подтверждения администратором."
                )
            else:
                await update.message.reply_text("❌ Неверный реферальный код")
        except Exception as e:
            logger.error(f"Error processing referral code: {e}")
            await update.message.reply_text("❌ Ошибка при обработке реферального кода.")

    async def get_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            telegram_id = update.effective_user.id
            name_input = update.message.text.strip()

            name_parts = name_input.split()
            if len(name_parts) < 2:
                await update.message.reply_text("Пожалуйста, введите Фамилию Имя Отчество:")
                return NAME

            registration_piece = {
                'full_name': name_input,
                'last_name': name_parts[0],
                'first_name': name_parts[1],
                'patronymic': name_parts[2] if len(name_parts) > 2 else ''
            }

            # Берём текущую сессию, аккуратно мёрджим данные
            session = db_manager.get_user_session(telegram_id) or {}
            current_reg = session.get('registration_data', {})
            current_reg.update(registration_piece)
            db_manager.update_user_session(telegram_id, current_step=EMAIL, registration_data=current_reg)

            await update.message.reply_text(
                "📧 Укажите ваш email (необязательно):\n"
                "Или отправьте '-' чтобы пропустить этот шаг."
            )
            return EMAIL
        except Exception as e:
            logger.error(f"Error in get_name: {e}")
            await update.message.reply_text("❌ Ошибка. Попробуйте еще раз.")
            return NAME

    async def get_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            telegram_id = update.effective_user.id
            email_input = update.message.text.strip()

            if email_input != '-':
                email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                if not re.match(email_regex, email_input):
                    await update.message.reply_text(
                        "❌ Неверный формат email. Введите корректный email или '-' чтобы пропустить:"
                    )
                    return EMAIL

            # Обновляем сессию аккуратно
            session = db_manager.get_user_session(telegram_id) or {}
            current_reg = session.get('registration_data', {})
            current_reg.update({'email': email_input if email_input != '-' else None})
            db_manager.update_user_session(telegram_id, current_step=PHONE, registration_data=current_reg)

            await update.message.reply_text(
                "📞 Укажите ваш номер телефона (необязательно):\n"
                "Или отправьте '-' чтобы пропустить этот шаг."
            )
            return PHONE
        except Exception as e:
            logger.error(f"Error in get_email: {e}")
            await update.message.reply_text("❌ Ошибка. Попробуйте еще раз.")
            return EMAIL

    async def get_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            telegram_id = update.effective_user.id
            phone_input = update.message.text.strip()

            if phone_input != '-':
                phone_digits = ''.join(filter(str.isdigit, phone_input))
                if len(phone_digits) < 10:
                    await update.message.reply_text(
                        "❌ Неверный формат телефона. Введите корректный номер или '-' чтобы пропустить:"
                    )
                    return PHONE

            # Обновляем сессию аккуратно
            session = db_manager.get_user_session(telegram_id) or {}
            current_reg = session.get('registration_data', {})
            current_reg.update({'phone': phone_input if phone_input != '-' else None})
            db_manager.update_user_session(telegram_id, current_step=COMPLETE, registration_data=current_reg)

            user_session = db_manager.get_user_session(telegram_id) or {'registration_data': current_reg}

            # Проверяем есть ли реферальный код в сессии
            referral_info = ""
            if user_session.get('registration_data', {}).get('referral_code'):
                referral_info = f"\n🔗 Реферальный код: {user_session['registration_data'].get('referral_code')}"

            confirmation_text = (
                "✅ Проверьте ваши данные:\n\n"
                f"👤 Имя: {user_session['registration_data'].get('full_name', 'Не указано')}\n"
                f"📧 Email: {user_session['registration_data'].get('email', 'Не указан') or 'Не указан'}\n"
                f"📞 Телефон: {user_session['registration_data'].get('phone', 'Не указан') or 'Не указан'}\n"
                f"🔗 Telegram: @{update.effective_user.username or 'Не указан'}"
                f"{referral_info}\n\n"
                "Всё верно? Отправьте 'Да' для подтверждения или 'Нет' для изменения данных."
            )

            await update.message.reply_text(confirmation_text)
            return COMPLETE
        except Exception as e:
            logger.error(f"Error in get_phone: {e}")
            await update.message.reply_text("❌ Ошибка. Попробуйте еще раз.")
            return PHONE

    async def complete_registration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            telegram_id = update.effective_user.id
            user_input = update.message.text.strip().lower()
            user_session = db_manager.get_user_session(telegram_id) or {}

            if user_input == 'нет':
                await update.message.reply_text(
                    "Давайте начнем заново. 📝\n\n"
                    "Как вас зовут? (Фамилия Имя Отчество):"
                )
                # Сбрасываем шаг в сессии
                db_manager.update_user_session(telegram_id, current_step=NAME, registration_data={})
                return NAME

            elif user_input == 'да':
                registration_data = user_session.get('registration_data', {})

                # Если у пользователя в Telegram есть username — используй его как username по умолчанию
                username = update.effective_user.username or f"user_{telegram_id}"

                try:
                    user_id, referral_code = db_manager.create_user(
                        telegram_id=telegram_id,
                        username=username,
                        first_name=registration_data.get('first_name'),
                        last_name=registration_data.get('last_name'),
                        patronymic=registration_data.get('patronymic'),
                        email=registration_data.get('email'),
                        phone=registration_data.get('phone')
                    )
                except Exception as e:
                    logger.error(f"Error creating user in DB: {e}")
                    user_id = None
                    referral_code = None

                if user_id:
                    # Обрабатываем реферальный код, если он есть
                    referral_code_used = registration_data.get('referral_code')
                    if referral_code_used:
                        try:
                            referrer = db_manager.get_user_by_referral_code(referral_code_used)
                            if referrer and referrer['telegram_id'] != telegram_id:
                                db_manager.create_referral(referrer['id'], user_id, referral_code_used)
                        except Exception as e:
                            logger.error(f"Error creating referral relation: {e}")

                    try:
                        db_manager.delete_user_session(telegram_id)
                    except Exception:
                        pass

                    success_text = (
                        "🎉 Регистрация завершена! 🎉\n\n"
                        f"✅ Ваш реферальный код: `{referral_code}`\n\n"
                        "📱 Поделитесь этим кодом с друзьями:\n"
                        "• Они получат скидку при регистрации\n"
                        "• Вы получите бонус на счет\n\n"
                        "🛠 Доступные команды:\n"
                        "/mycode - ваш реферальный код\n"
                        "/myref - реферальная ссылка и QR-код\n"
                        "/balance - ваш баланс\n"
                        "/referrals - ваши рефералы\n"
                        "/adminpanel - админ панель\n\n"
                        "Спасибо за регистрацию! 🚀"
                    )

                    await update.message.reply_text(success_text)

                else:
                    await update.message.reply_text(
                        "❌ Произошла ошибка при регистрации. "
                        "Пожалуйста, попробуйте снова: /start"
                    )

                return ConversationHandler.END

            else:
                await update.message.reply_text(
                    "Пожалуйста, ответьте 'Да' или 'Нет':\n"
                    "✅ 'Да' - завершить регистрацию\n"
                    "❌ 'Нет' - изменить данных"
                )
                return COMPLETE
        except Exception as e:
            logger.error(f"Error in complete_registration: {e}")
            await update.message.reply_text("❌ Ошибка при регистрации. Попробуйте снова: /start")
            return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            telegram_id = update.effective_user.id
            db_manager.delete_user_session(telegram_id)

            await update.message.reply_text(
                "Регистрация отменена. 😔\n\n"
                "Если захотите зарегистрироваться, просто отправьте /start"
            )
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"Error in cancel: {e}")
            return ConversationHandler.END

    async def my_referral_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            telegram_id = update.effective_user.id
            user = db_manager.get_user_by_telegram_id(telegram_id)

            if user:
                await update.message.reply_text(
                    f"🎯 Ваш реферальный код:\n\n"
                    f"`{user['referral_code']}`\n\n"
                    f"Поделитесь этим кодом с друзьями! 💫\n\n"
                    f"Используйте /myref чтобы получить QR-код и ссылку"
                )
            else:
                await update.message.reply_text(
                    "❌ Вы еще не зарегистрированы.\n"
                    "Используйте /start для регистрации."
                )
        except Exception as e:
            logger.error(f"Error in my_referral_code: {e}")
            await update.message.reply_text("❌ Ошибка при получении кода.")

    async def my_referral_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает реферальную ссылку и QR-код"""
        try:
            telegram_id = update.effective_user.id
            user = db_manager.get_user_by_telegram_id(telegram_id)

            if not user:
                await update.message.reply_text(
                    "❌ Вы еще не зарегистрированы.\n"
                    "Используйте /start для регистрации."
                )
                return

            referral_code = user['referral_code']
            referral_link = self.generate_referral_link(referral_code)

            # Генерируем QR-код
            qr_code = self.generate_qr_code(referral_link)

            message_text = (
                "🎁 Ваши реферальные материалы:\n\n"
                f"🔗 **Ссылка:**\n`{referral_link}`\n\n"
                f"📝 **Код:** `{referral_code}`\n\n"
                "📱 **Поделитесь с друзьями:**\n"
                "• Отправьте ссылку или QR-код\n"
                "• При регистрации по вашей ссылке друг получит скидку\n"
                "• Вы получите бонус после подтверждения администратором"
            )

            # Отправляем QR-код как фото и текст
            await update.message.reply_photo(
                photo=qr_code,
                caption=message_text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error in my_referral_link: {e}")
            await update.message.reply_text("❌ Ошибка при генерации ссылки.")

    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            telegram_id = update.effective_user.id
            user = db_manager.get_user_by_telegram_id(telegram_id)

            if user:
                referrals_count = db_manager.get_user_referrals(user['id'])

                await update.message.reply_text(
                    f"💰 Ваш баланс: {user.get('bonus_balance', 0)} руб.\n\n"
                    f"👥 Приведено друзей: {len(referrals_count)}\n"
                    f"💎 Реферальный код: `{user['referral_code']}`"
                )
            else:
                await update.message.reply_text(
                    "❌ Вы еще не зарегистрированы.\n"
                    "Используйте /start для регистрации."
                )
        except Exception as e:
            logger.error(f"Error in balance: {e}")
            await update.message.reply_text("❌ Ошибка при получении баланса.")

    async def my_referrals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            telegram_id = update.effective_user.id
            user = db_manager.get_user_by_telegram_id(telegram_id)

            if user:
                referrals = db_manager.get_user_referrals(user['id'])

                if referrals:
                    referrals_text = "👥 Ваши рефералы:\n\n"
                    for i, referral in enumerate(referrals, 1):
                        status = "✅ Бонус выплачен" if referral.get('bonus_paid') else "⏳ Ожидает выплаты"
                        referrals_text += f"{i}. {referral.get('referred_username')} - {status}\n"

                    await update.message.reply_text(referrals_text)
                else:
                    await update.message.reply_text(
                        "😔 У вас пока нет рефералов.\n\n"
                        f"Поделитесь вашим кодом: `{user['referral_code']}`\n"
                        "или используйте /myref для получения ссылки и QR-кода\n"
                        "и приглашайте друзей! 🚀"
                    )
            else:
                await update.message.reply_text(
                    "❌ Вы еще не зарегистрированы.\n"
                    "Используйте /start для регистрации."
                )
        except Exception as e:
            logger.error(f"Error in my_referrals: {e}")
            await update.message.reply_text("❌ Ошибка при получении списка рефералов.")

    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            telegram_id = update.effective_user.id

            if not db_manager.is_admin(telegram_id):
                await update.message.reply_text(
                    "❌ У вас нет доступа к админ-панели.\n"
                    "Обратитесь к администратору системы."
                )
                return

            stats = db_manager.get_admin_stats()

            admin_text = (
                "🔧 Админ Панель\n\n"
                f"👥 Всего пользователей: {stats.get('total_users', 0)}\n"
                f"📊 Всего рефералов: {stats.get('total_referrals', 0)}\n"
                f"💰 Невыплаченные бонусы: {stats.get('unpaid_bonuses', 0)}\n"
                f"✅ Выплаченные бонусы: {stats.get('total_bonus_paid', 0)}\n\n"
            )

            keyboard = [
                [InlineKeyboardButton("📊 Обновить статистику", callback_data="admin_refresh")],
                [InlineKeyboardButton("📋 Список невыплаченных", callback_data="admin_unpaid")],
                [InlineKeyboardButton("📤 Экспорт в Excel", callback_data="admin_export")],
                [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(admin_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error in admin_panel: {e}")
            await update.message.reply_text("❌ Ошибка при открытии админ-панели.")

    async def admin_button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопок админ-панели"""
        try:
            query = update.callback_query
            await query.answer()

            telegram_id = query.from_user.id

            if not db_manager.is_admin(telegram_id):
                await query.edit_message_text("❌ Нет доступа")
                return

            data = query.data
            logger.info(f"Admin button pressed: {data}")

            if data == "admin_refresh":
                stats = db_manager.get_admin_stats()
                admin_text = (
                    "🔧 Админ Панель (обновлено)\n\n"
                    f"👥 Всего пользователей: {stats.get('total_users', 0)}\n"
                    f"📊 Всего рефералов: {stats.get('total_referrals', 0)}\n"
                    f"💰 Невыплаченные бонусы: {stats.get('unpaid_bonuses', 0)}\n"
                    f"✅ Выплаченные бонусы: {stats.get('total_bonus_paid', 0)}\n\n"
                )

                keyboard = [
                    [InlineKeyboardButton("📊 Обновить статистику", callback_data="admin_refresh")],
                    [InlineKeyboardButton("📋 Список невыплаченных", callback_data="admin_unpaid")],
                    [InlineKeyboardButton("📤 Экспорт в Excel", callback_data="admin_export")],
                    [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.edit_message_text(admin_text, reply_markup=reply_markup)

            elif data == "admin_unpaid":
                unpaid_referrals = db_manager.get_unpaid_referrals()

                if not unpaid_referrals:
                    await query.edit_message_text(
                        "📋 Нет невыплаченных бонусов\n\n"
                        "Все рефералы уже обработаны! ✅"
                    )
                    return

                # Отправляем отдельное сообщение со списком
                unpaid_text = "📋 Невыплаченные бонусы:\n\n"
                for i, referral in enumerate(unpaid_referrals, 1):
                    referral_date = referral.get('referral_date')
                    if hasattr(referral_date, 'strftime'):
                        date_str = referral_date.strftime('%d.%m.%Y %H:%M')
                    else:
                        date_str = str(referral_date)
                    unpaid_text += (
                        f"{i}. 👤 {referral.get('referrer_name')}\n"
                        f"   👥 Привел: {referral.get('referred_name')}\n"
                        f"   📅 {date_str}\n"
                        f"   [ID: {referral.get('id')}]\n\n"
                    )

                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=unpaid_text
                )

                # Отправляем кнопки для выплат
                for referral in unpaid_referrals:
                    keyboard = [[InlineKeyboardButton(
                        f"💸 Выплатить бонус {referral.get('referrer_name')}",
                        callback_data=f"pay_{referral.get('id')}"
                    )]]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    await context.bot.send_message(
                        chat_id=telegram_id,
                        text=f"Бонус для {referral.get('referrer_name')} - {referral.get('referred_name')}",
                        reply_markup=reply_markup
                    )

            elif data == "admin_export":
                try:
                    excel_file = db_manager.export_to_excel()
                    await context.bot.send_document(
                        chat_id=telegram_id,
                        document=excel_file,
                        filename="referral_data.xlsx",
                        caption="📊 Экспорт данных в Excel"
                    )
                except Exception as e:
                    await query.edit_message_text(f"❌ Ошибка при экспорте: {e}")

            elif data == "admin_users":
                # Получаем список пользователей и показываем краткую карточку с кнопками
                users = db_manager.get_all_users()
                if not users:
                    await query.edit_message_text("👥 Пользователи не найдены.")
                    return

                # Ограничим вывод первых 30 пользователей (не перегружать чат)
                for u in users[:30]:
                    username = u.get('username') or f"user_{u.get('telegram_id')}"
                    text = (
                        f"👤 @{username}\n"
                        f"ID: {u.get('telegram_id')}\n"
                        f"Email: {u.get('email') or 'Не указан'}\n"
                        f"Тел: {u.get('phone') or 'Не указан'}\n"
                    )
                    kb = [
                        [InlineKeyboardButton("Открыть чат", url=f"https://t.me/{username}")],
                        [InlineKeyboardButton("Ввести номер вручную", callback_data=f"admin_user_enternum_{u.get('telegram_id')}")]
                    ]
                    reply_markup = InlineKeyboardMarkup(kb)
                    await context.bot.send_message(chat_id=telegram_id, text=text, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error in admin_button_handler: {e}")
            try:
                await query.edit_message_text("❌ Ошибка при обработке запроса.")
            except Exception:
                pass

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопок выплат и кнопок пользователей (ввод номера)"""
        try:
            query = update.callback_query
            await query.answer()

            telegram_id = query.from_user.id

            if not db_manager.is_admin(telegram_id):
                await query.edit_message_text("❌ Нет доступа")
                return

            data = query.data

            # Выплата бонуса
            if data.startswith("pay_"):
                referral_id = int(data.replace("pay_", ""))
                logger.info(f"Paying bonus for referral: {referral_id}")

                success = db_manager.mark_bonus_paid(referral_id, telegram_id)

                if success:
                    await query.edit_message_text(
                        "✅ Бонус успешно выплачен!\n\n"
                        "Статус обновлен в системе."
                    )
                else:
                    await query.edit_message_text(
                        "❌ Ошибка при выплате бонуса.\n"
                        "Возможно, бонус уже был выплачен."
                    )
                return

            # Обработка ввода номера вручную (админ)
            if data.startswith("admin_user_enternum_"):
                # Формат callback: admin_user_enternum_<telegram_id>
                try:
                    target_telegram_id = int(data.replace("admin_user_enternum_", ""))
                except ValueError:
                    await query.edit_message_text("❌ Неправильный ID пользователя.")
                    return

                # Подсказка админу: используйте команду /setphone <telegram_id> <номер>
                await query.edit_message_text(
                    f"Введите команду для установки номера пользователю:\n"
                    f"/setphone {target_telegram_id} <номер>\n\n"
                    f"Пример: /setphone {target_telegram_id} +79001234567"
                )
                return

        except Exception as e:
            logger.error(f"Error in button_handler: {e}")
            try:
                await query.edit_message_text("❌ Ошибка при обработке кнопки.")
            except Exception:
                pass

    async def export_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            telegram_id = update.effective_user.id

            if not db_manager.is_admin(telegram_id):
                await update.message.reply_text("❌ У вас нет доступа к этой команде.")
                return

            try:
                excel_file = db_manager.export_to_excel()
                await update.message.reply_document(
                    document=excel_file,
                    filename="referral_data.xlsx",
                    caption="📊 Экспорт данных в Excel"
                )
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка при экспорте: {e}")
        except Exception as e:
            logger.error(f"Error in export_data: {e}")
            await update.message.reply_text("❌ Ошибка при экспорте.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик любых сообщений"""
        try:
            text = update.message.text.lower().strip()

            # Обработка специальной команды /setphone, если админ вводит ее как обычное сообщение (fallback)
            if text.startswith('/setphone'):
                return await self.set_phone_command(update, context)

            if text in ['start', 'старт']:
                return await self.start(update, context)
            elif text in ['помощь', 'help', 'команды']:
                await update.message.reply_text(
                    "🤖 Я бот реферальной системы!\n\n"
                    "Используйте команды:\n"
                    "/start - регистрация в системе\n"
                    "/mycode - ваш реферальный код\n"
                    "/myref - ваша реферальная ссылка и QR-код\n"
                    "/balance - ваш баланс бонусов\n"
                    "/referrals - ваши рефералы\n"
                    "/adminpanel - админ панель"
                )
            else:
                await update.message.reply_text(
                    "🤖 Я не понимаю эту команду.\n\n"
                    "Используйте /start для регистрации или /help для списка команд."
                )
        except Exception as e:
            logger.error(f"Error in handle_message: {e}")
            await update.message.reply_text("❌ Произошла ошибка. Попробуйте еще раз.")

    async def set_phone_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Команда для админа: /setphone <telegram_id> <номер>
        Устанавливает/обновляет номер телефона для пользователя с данным telegram_id.
        """
        try:
            telegram_id = update.effective_user.id
            if not db_manager.is_admin(telegram_id):
                await update.message.reply_text("❌ У вас нет прав для этой команды.")
                return

            # Разбираем аргументы
            args = context.args if hasattr(context, 'args') else []
            if not args or len(args) < 2:
                await update.message.reply_text("Использование: /setphone <telegram_id> <номер>\nПример: /setphone 123456789 +79001234567")
                return

            try:
                target_telegram_id = int(args[0])
            except ValueError:
                await update.message.reply_text("❌ Неправильный telegram_id.")
                return

            number = args[1]
            # Валидация номера — только цифры и +
            number_digits = ''.join(filter(lambda c: c.isdigit() or c == '+', number))
            if len(''.join(filter(str.isdigit, number_digits))) < 10:
                await update.message.reply_text("❌ Неправильный формат номера.")
                return

            # Попытка обновить номер в БД — предполагаем, что db_manager имеет метод для этого
            try:
                updated = False
                # Пробуем несколько возможных имён функции в db_manager (на случай, если в вашей реализации кот. другое имя)
                if hasattr(db_manager, 'update_user_phone'):
                    updated = db_manager.update_user_phone(target_telegram_id, number_digits)
                elif hasattr(db_manager, 'set_user_phone'):
                    updated = db_manager.set_user_phone(target_telegram_id, number_digits)
                elif hasattr(db_manager, 'update_user_by_telegram_id'):
                    # общий метод, передаём словарь полей
                    updated = db_manager.update_user_by_telegram_id(target_telegram_id, {'phone': number_digits})
                else:
                    # Если нет подходящих методов — пробуем получить user и сохранить через create_user (рискованно)
                    user = db_manager.get_user_by_telegram_id(target_telegram_id)
                    if user:
                        db_manager.update_user_phone_in_record = True  # no-op marker; реальная функция может отсутствовать
                        # если нет метода, сообщим админу
                        await update.message.reply_text("❌ На стороне db_manager нет метода для обновления телефона. Пожалуйста, добавьте update_user_phone(telegram_id, phone).")
                        return

                if updated:
                    await update.message.reply_text("✅ Номер успешно обновлён.")
                else:
                    # Если метод вернул False или None — всё равно сообщим
                    await update.message.reply_text("✅ Попытка обновления выполнена (проверьте, применился ли номер в БД).")
            except Exception as e:
                logger.error(f"Error updating phone in DB: {e}")
                await update.message.reply_text("❌ Ошибка при обновлении номера в БД.")
        except Exception as e:
            logger.error(f"Error in set_phone_command: {e}")
            await update.message.reply_text("❌ Ошибка при обработке команды /setphone.")

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        try:
            logger.error(f"Exception while handling an update: {context.error}")

            # Пытаемся отправить сообщение об ошибке пользователю
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "❌ Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."
                )
        except Exception as e:
            logger.error(f"Error in error_handler: {e}")

    def setup_handlers(self):
        """Настройка всех обработчиков"""
        # Обработчик регистрации
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler('start', self.start),
                MessageHandler(filters.TEXT & filters.Regex(r'^(start|старт)$'), self.start_text)
            ],
            states={
                NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_name)],
                EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_email)],
                PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_phone)],
                COMPLETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.complete_registration)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel)],
        )

        # Команды
        self.application.add_handler(conv_handler)
        self.application.add_handler(CommandHandler("mycode", self.my_referral_code))
        self.application.add_handler(CommandHandler("myref", self.my_referral_link))
        self.application.add_handler(CommandHandler("balance", self.balance))
        self.application.add_handler(CommandHandler("referrals", self.my_referrals))
        self.application.add_handler(CommandHandler("adminpanel", self.admin_panel))
        self.application.add_handler(CommandHandler("export", self.export_data))
        self.application.add_handler(CommandHandler("help", self.handle_message))
        # Команда для установки номера админом
        self.application.add_handler(CommandHandler("setphone", self.set_phone_command))

        # Обработчики кнопок
        self.application.add_handler(CallbackQueryHandler(self.admin_button_handler, pattern="^admin_"))
        self.application.add_handler(CallbackQueryHandler(self.button_handler, pattern="^(pay_|admin_user_enternum_)"))

        # Обработчик любых сообщений (должен быть последним)
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        # Обработчик ошибок
        self.application.add_error_handler(self.error_handler)
