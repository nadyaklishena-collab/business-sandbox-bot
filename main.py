import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from telegram import (
    Bot,
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    ParseMode,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    ConversationHandler,
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ---- ЛОГИ ----
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---- СТАНИ ДЛЯ CONVERSATION HANDLER ----
(
    WAIT_START,
    POLICY,
    LANGUAGE,
    NAME,
    PHONE,
    PHONE_MANUAL,
    CITY,
    FIELD,
    EXPERIENCE,
) = range(9)

# ---- ЗАГРУЗКА НАСТРОЕК ИЗ .env ----
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Registrations")

# Гиперссылка на политику (HTML)
POLICY_URL = (
    "https://docs.google.com/document/d/1zeC9FBAj3XRQ0PwPcIRZJ5CSQnTh2AjH8pvB599RMO8/edit"
)

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN / BOT_TOKEN не знайдено в .env")
if not SPREADSHEET_ID:
    raise RuntimeError("SPREADSHEET_ID не знайдено в .env")


# ---- GOOGLE SHEETS ----
def init_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
    return sheet


sheet = init_sheet()


def append_row(data: dict):
    """
    Додаємо рядок у Google Sheets відповідно до структури:

    timestamp	user_id	username	first_name	segment	name	phone	city	field	experience	source
    """
    try:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        row = [
            timestamp,                   # timestamp
            data.get("user_id", ""),     # user_id
            data.get("username", ""),    # username
            data.get("first_name", ""),  # first_name
            data.get("lang", ""),        # segment (ua/ru)
            data.get("name", ""),        # name
            data.get("phone", ""),       # phone
            data.get("city", ""),        # city
            data.get("field", ""),       # field
            data.get("experience", ""),  # experience
            "telegram",                  # source
        ]

        sheet.append_row(row)

    except Exception as e:
        logger.exception(f"Помилка запису в Google Sheets: {e}")


# ---- ТЕКСТИ ----

WELCOME_UA = (
    "Привіт! 👋\n"
    "Ми запускаємо Business Sandbox — безкоштовну бізнес-школу для українців в Орхусі.\n"
    "(навчання українською або російською мовами)\n\n"
    "Ми проводимо попередній запис на перший потік, де Ви зможете отримати практичні знання про:\n\n"
    "• датське законодавство\n"
    "• податки\n"
    "• маркетинг\n"
    "• ділову датську мову\n"
    "та багато іншого ✨\n\n"
    "А ще — безпечно протестувати свою бізнес-ідею ⭐️\n\n"
    "Щоб почати — натисніть кнопку «Старт»."
)

POLICY_UA = (
    "Перш ніж ми почнемо 😊\n\n"
    "Натискаючи «Почати» та продовжуючи реєстрацію, Ви погоджуєтеся на обробку Ваших "
    "персональних даних (ім’я, телефон, місто, сфера діяльності).\n\n"
    "Ці дані використовуються для зв'язку з Вами щодо участі в проєкті.\n\n"
    "Ваші дані можуть бути видалені за Вашим зверненням.\n\n"
    'Повна версія політики та згоди: <a href="{url}">прочитати тут</a>.'
)

LANG_CHOICE = "Будь ласка, оберіть мову спілкування:"
LANG_KB = [["🇺🇦 Українська"], ["🇷🇺 Русский"]]


def is_ua(lang: str) -> bool:
    return lang == "ua"


def clean_text(text: str) -> str:
    return (text or "").strip()


# ---- ОБРАБОТЧИКИ ----

def start(update: Update, context: CallbackContext) -> int:
    """Початок розмови, показуємо привітання і кнопку Старт."""
    user = update.effective_user
    logger.info("Start by %s", user.id if user else "unknown")

    context.user_data.clear()

    kb = [["Старт"]]
    reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)

    update.message.reply_text(WELCOME_UA, reply_markup=reply_markup)
    return WAIT_START


def wait_start(update: Update, context: CallbackContext) -> int:
    """Чекаємо натискання Старт. Будь-який інший текст не приймається."""
    text = clean_text(update.message.text)

    if text != "Старт":
        update.message.reply_text("Щоб розпочати, натисніть, будь ласка, кнопку «Старт».")
        return WAIT_START

    kb = [["Погоджуюсь"], ["Не погоджуюсь"]]
    reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)

    update.message.reply_text(
        POLICY_UA.format(url=POLICY_URL),
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )
    return POLICY


def policy_handler(update: Update, context: CallbackContext) -> int:
    """Обробка згоди / незгоди з політикою. Тут тільки кнопки."""
    text = clean_text(update.message.text)

    if text == "Погоджуюсь":
        reply_markup = ReplyKeyboardMarkup(
            LANG_KB, resize_keyboard=True, one_time_keyboard=True
        )
        update.message.reply_text(LANG_CHOICE, reply_markup=reply_markup)
        return LANGUAGE

    if text == "Не погоджуюсь":
        kb = [["Старт"]]
        reply_markup = ReplyKeyboardMarkup(
            kb, resize_keyboard=True, one_time_keyboard=True
        )
        update.message.reply_text(
            "Дякуємо! Без згоди на обробку даних ми не можемо продовжити реєстрацію.\n\n"
            "Якщо передумаєте — натисніть «Старт» і почніть заново.",
            reply_markup=reply_markup,
        )
        return WAIT_START

    # Жорстко: тільки кнопки
    update.message.reply_text(
        "Будь ласка, оберіть один із варіантів: «Погоджуюсь» або «Не погоджуюсь» за допомогою кнопок."
    )
    return POLICY


def language_handler(update: Update, context: CallbackContext) -> int:
    """Вибір мови. Тільки кнопки 🇺🇦 або 🇷🇺."""
    text = clean_text(update.message.text)

    if text == "🇺🇦 Українська":
        context.user_data["lang"] = "ua"
    elif text == "🇷🇺 Русский":
        context.user_data["lang"] = "ru"
    else:
        update.message.reply_text("Будь ласка, оберіть мову за допомогою кнопок.")
        return LANGUAGE

    lang = context.user_data["lang"]
    user = update.effective_user

    if user:
        context.user_data["user_id"] = user.id
        context.user_data["username"] = user.username or ""
        context.user_data["first_name"] = user.first_name or ""

    # Далі вже текстовий ввід ІМЕНІ дозволений
    if is_ua(lang):
        update.message.reply_text(
            "Як Вас звати? (Напишіть Ваше ім'я текстом)", reply_markup=ReplyKeyboardRemove()
        )
    else:
        update.message.reply_text(
            "Как Вас зовут? (Напишите Ваше имя текстом)", reply_markup=ReplyKeyboardRemove()
        )

    return NAME


def name_handler(update: Update, context: CallbackContext) -> int:
    """Зберігаємо ім'я, питаємо телефон (кнопка/вручну). Тут текст дозволений."""
    lang = context.user_data.get("lang", "ua")
    name = clean_text(update.message.text)
    if not name:
        if is_ua(lang):
            update.message.reply_text("Будь ласка, введіть Ваше ім'я текстом.")
        else:
            update.message.reply_text("Пожалуйста, введите Ваше имя текстом.")
        return NAME

    context.user_data["name"] = name

    if is_ua(lang):
        share_btn = KeyboardButton("📱 Поділитися контактом", request_contact=True)
        manual_btn = KeyboardButton("📞 Ввести номер вручну")
        text = (
            "Будь ласка, поділіться Вашим номером телефону.\n\n"
            "Можете натиснути «📱 Поділитися контактом» або «📞 Ввести номер вручну»."
        )
    else:
        share_btn = KeyboardButton("📱 Поделиться контактом", request_contact=True)
        manual_btn = KeyboardButton("📞 Ввести номер вручную")
        text = (
            "Пожалуйста, поделитесь Вашим номером телефона.\n\n"
            "Можете нажать «📱 Поделиться контактом» или «📞 Ввести номер вручную»."
        )

    reply_markup = ReplyKeyboardMarkup(
        [[share_btn], [manual_btn]], resize_keyboard=True, one_time_keyboard=True
    )

    update.message.reply_text(text, reply_markup=reply_markup)
    return PHONE


def phone_handler(update: Update, context: CallbackContext) -> int:
    """
    Отримуємо телефон:
    - або контакт (request_contact),
    - або переходимо до ручного вводу за кнопкою.
    Будь-який інший текст відхиляємо.
    """
    lang = context.user_data.get("lang", "ua")

    # Вариант 1: отправили контакт
    if update.message.contact:
        phone = update.message.contact.phone_number
        context.user_data["phone"] = phone

        if is_ua(lang):
            update.message.reply_text(
                "Дякуємо! 🙌\n\nВ якому місті Ви зараз проживаєте?",
                reply_markup=ReplyKeyboardRemove(),
            )
        else:
            update.message.reply_text(
                "Спасибо! 🙌\n\nВ каком городе Вы сейчас живёте?",
                reply_markup=ReplyKeyboardRemove(),
            )
        return CITY

    # Вариант 2: натиснули кнопку "Ввести номер вручну"
    text = clean_text(update.message.text)

    if is_ua(lang) and text == "📞 Ввести номер вручну":
        update.message.reply_text(
            "Будь ласка, введіть Ваш номер у форматі +45 00 00 00 00.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return PHONE_MANUAL

    if not is_ua(lang) and text == "📞 Ввести номер вручную":
        update.message.reply_text(
            "Пожалуйста, введите Ваш номер в формате +45 00 00 00 00.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return PHONE_MANUAL

    # Інший текст не приймаємо — тільки кнопки
    if is_ua(lang):
        update.message.reply_text(
            "Будь ласка, скористайтеся кнопками: «📱 Поділитися контактом» "
            "або «📞 Ввести номер вручну»."
        )
    else:
        update.message.reply_text(
            "Пожалуйста, используйте кнопки: «📱 Поделиться контактом» "
            "или «📞 Ввести номер вручную»."
        )
    return PHONE


def phone_manual_handler(update: Update, context: CallbackContext) -> int:
    """Ручний ввід номера телефону. Тут текст дозволений, але з перевіркою."""
    lang = context.user_data.get("lang", "ua")
    phone = clean_text(update.message.text)

    digits = [c for c in phone if c.isdigit()]
    if not phone.startswith("+") or len(digits) < 8:
        if is_ua(lang):
            update.message.reply_text(
                "Схоже, номер у некоректному форматі.\n"
                "Приклад: +45 00 00 00 00\n"
                "Спробуйте, будь ласка, ще раз."
            )
        else:
            update.message.reply_text(
                "Похоже, номер в неверном формате.\n"
                "Пример: +45 00 00 00 00\n"
                "Попробуйте, пожалуйста, ещё раз."
            )
        return PHONE_MANUAL

    context.user_data["phone"] = phone

    if is_ua(lang):
        update.message.reply_text(
            "Дякуємо! 🙌\n\nВ якому місті Ви зараз проживаєте?",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        update.message.reply_text(
            "Спасибо! 🙌\n\nВ каком городе Вы сейчас живёте?",
            reply_markup=ReplyKeyboardRemove(),
        )
    return CITY


def city_handler(update: Update, context: CallbackContext) -> int:
    """Отримуємо місто. Тут текст дозволений."""
    lang = context.user_data.get("lang", "ua")
    city = clean_text(update.message.text)
    if not city:
        if is_ua(lang):
            update.message.reply_text("Будь ласка, напишіть назву міста текстом.")
        else:
            update.message.reply_text("Пожалуйста, напишите название города текстом.")
        return CITY

    context.user_data["city"] = city

    # Далі тільки кнопки по сферам
    if is_ua(lang):
        kb = [["Б'юті", "Ресторанний бізнес"], ["Клінінг", "Інше"]]
        text = "У якій сфері Ви плануєте або хотіли б працювати?"
    else:
        kb = [["Бьюти", "Ресторанный бизнес"], ["Клининг", "Другое"]]
        text = "В какой сфере Вы планируете или хотели бы работать?"

    reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text(text, reply_markup=reply_markup)
    return FIELD


def field_handler(update: Update, context: CallbackContext) -> int:
    """
    Отримуємо сферу.
    ТУТ ЖОРСТКО: тільки кнопки, свої варіанти не приймаємо.
    """
    lang = context.user_data.get("lang", "ua")
    field = clean_text(update.message.text)

    if is_ua(lang):
        allowed = ["Б'юті", "Ресторанний бізнес", "Клінінг", "Інше"]
        error_text = "Будь ласка, оберіть сферу за допомогою кнопок."
    else:
        allowed = ["Бьюти", "Ресторанный бизнес", "Клининг", "Другое"]
        error_text = "Пожалуйста, выберите сферу с помощью кнопок."

    if field not in allowed:
        update.message.reply_text(error_text)
        return FIELD

    context.user_data["field"] = field

    if is_ua(lang):
        kb = [["Так", "Ні"]]
        text = "Чи є у Вас досвід в цій сфері?"
    else:
        kb = [["Да", "Нет"]]
        text = "Есть ли у Вас опыт в этой сфере?"

    reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text(text, reply_markup=reply_markup)
    return EXPERIENCE


def experience_handler(update: Update, context: CallbackContext) -> int:
    """Отримуємо відповідь про досвід (лише кнопки)."""
    lang = context.user_data.get("lang", "ua")
    text = clean_text(update.message.text)

    if is_ua(lang):
        allowed = ("Так", "Ні")
        error_text = "Будь ласка, оберіть один із варіантів: «Так» або «Ні» за допомогою кнопок."
    else:
        allowed = ("Да", "Нет")
        error_text = "Пожалуйста, выберите: «Да» или «Нет» с помощью кнопок."

    if text not in allowed:
        update.message.reply_text(error_text)
        return EXPERIENCE

    context.user_data["experience"] = text

    # Запис у таблицю
    append_row(context.user_data)

    if is_ua(lang):
        final_text = (
            "Дякуємо Вам за реєстрацію! 💛\n\n"
            "Ми зв'яжемося з Вами у березні, перед запуском школи, "
            "або раніше — якщо строки зміняться."
        )
        again_text = "У разі, якщо Ваша інформація змінилась - Ви можете пройти реєстрацію ще раз, натисніть /start."
    else:
        final_text = (
            "Благодарим Вас за регистрацию! 💛\n\n"
            "Мы свяжемся с Вами в марте, перед запуском школы, "
            "или раньше — если сроки изменятся."
        )
        again_text = "Если Ваша информация изменилась, Ви можете пройти регестрацию еще раз, нажмите /start."

    update.message.reply_text(final_text, reply_markup=ReplyKeyboardRemove())
    update.message.reply_text(again_text)

    context.user_data.clear()
    return ConversationHandler.END


def cancel(update: Update, context: CallbackContext) -> int:
    """Скасування діалогу."""
    update.message.reply_text(
        "Реєстрацію скасовано. Якщо захочете почати знову — натисніть /start.",
        reply_markup=ReplyKeyboardRemove(),
    )
    context.user_data.clear()
    return ConversationHandler.END


def main():
    bot = Bot(token=BOT_TOKEN)
    updater = Updater(bot=bot, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAIT_START: [MessageHandler(Filters.text & ~Filters.command, wait_start)],
            POLICY: [MessageHandler(Filters.text & ~Filters.command, policy_handler)],
            LANGUAGE: [MessageHandler(Filters.text & ~Filters.command, language_handler)],
            NAME: [MessageHandler(Filters.text & ~Filters.command, name_handler)],
            PHONE: [
                MessageHandler(Filters.contact, phone_handler),
                MessageHandler(Filters.text & ~Filters.command, phone_handler),
            ],
            PHONE_MANUAL: [
                MessageHandler(Filters.text & ~Filters.command, phone_manual_handler)
            ],
            CITY: [MessageHandler(Filters.text & ~Filters.command, city_handler)],
            FIELD: [MessageHandler(Filters.text & ~Filters.command, field_handler)],
            EXPERIENCE: [
                MessageHandler(Filters.text & ~Filters.command, experience_handler)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    dp.add_handler(conv_handler)

    logger.info("Bot is starting...")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
