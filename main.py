import logging
import os
import re
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
    ConversationHandler,
    CallbackContext,
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ---------------- ЛОГИ ----------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------- СТАНИ ----------------

(
    LANGUAGE,
    CONSENT,
    NAME,
    PHONE_METHOD,
    PHONE_MANUAL,
    CITY,
    FIELD,
    EXPERIENCE,
) = range(8)

# ---------------- НАСТРОЙКИ ----------------

load_dotenv()

BOT_TOKEN = (
    os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("TELEGRAM_TOKEN")
)
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Registrations")

PRIVACY_URL = "https://docs.google.com/document/d/1zeC9FBAj3XRQ0PwPcIRZJ5CSQnTh2AjH8pvB599RMO8/edit?tab=t.0"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN / TELEGRAM_BOT_TOKEN не найден в .env")
if not SPREADSHEET_ID:
    raise RuntimeError("SPREADSHEET_ID не найден в .env")

# ---------------- GOOGLE SHEETS ----------------


def init_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name("CREDS_JSON", scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
    return sheet


sheet = init_sheet()

# ---------------- ТЕКСТЫ ----------------


def t(key: str, lang: str) -> str:
    return TEXTS[key][lang]


TEXTS = {
    "lang_choose": {
        "uk": "Оберіть мову / Выберите язык:",
        "ru": "Оберите язык / Выберите язык:",
    },
    "welcome": {
        "uk": (
            "Привіт! 👋\n\n"
            "Це реєстраційний бот Business Sandbox Aarhus.\n"
            "Щоб почати — натисніть кнопку «Почати»."
        ),
        "ru": (
            "Привет! 👋\n\n"
            "Это регистрационный бот Business Sandbox Aarhus.\n"
            "Чтобы начать — нажмите кнопку «Начать»."
        ),
    },
    "policy": {
        "uk": (
            "Перш ніж ми почнемо 😊\n\n"
            "Натискаючи «Погоджуюсь» та продовжуючи реєстрацію, "
            "Ви погоджуєтеся на обробку Ваших персональних даних "
            "(ім’я, телефон, місто, сфера діяльності).\n\n"
            "Ці дані використовуються для зв'язку з Вами щодо участі в проєкті.\n"
            "Ваші дані можуть бути видалені за Вашим зверненням.\n\n"
            f"Повна версія політики та згоди: "
            f'<a href="{PRIVACY_URL}">прочитати тут</a>.'
        ),
        "ru": (
            "Прежде чем мы начнём 😊\n\n"
            "Нажимая «Согласен» и продолжая регистрацию, "
            "Вы соглашаетесь на обработку Ваших персональных данных "
            "(имя, телефон, город, сфера деятельности).\n\n"
            "Эти данные используются для связи с Вами по участию в проекте.\n"
            "Ваши данные могут быть удалены по Вашему запросу.\n\n"
            f"Полная версия политики и согласия: "
            f'<a href="{PRIVACY_URL}">прочитать здесь</a>.'
        ),
    },
    "no_consent": {
        "uk": (
            "Дякуємо! Без згоди на обробку даних ми не можемо продовжити реєстрацію.\n\n"
            "Якщо передумаєте — надішліть /start і почніть заново."
        ),
        "ru": (
            "Благодарим! Без согласия на обработку данных мы не можем продолжить регистрацию.\n\n"
            "Если передумаете — отправьте /start и начните заново."
        ),
    },
    "ask_name": {
        "uk": "Як Вас звати? 🙂\nНапишіть, будь ласка, Ваше ім’я.",
        "ru": "Как Вас зовут? 🙂\nПожалуйста, напишите Ваше имя.",
    },
    "ask_phone_method": {
        "uk": "Як зручніше залишити номер телефону? 📱",
        "ru": "Как удобнее оставить номер телефона? 📱",
    },
    "ask_phone_manual": {
        "uk": (
            "Введіть, будь ласка, номер телефону у міжнародному форматі.\n"
            "Наприклад: +45 12345678 або +380 991234567"
        ),
        "ru": (
            "Пожалуйста, введите номер телефона в международном формате.\n"
            "Например: +45 12345678 или +380 991234567"
        ),
    },
    "phone_invalid": {
        "uk": (
            "Номер виглядає некоректним 🤔\n"
            "Будь ласка, введіть номер у форматі +КОД_КРАЇНИ і тільки цифри.\n"
            "Наприклад: +45 12345678 або +380 991234567."
        ),
        "ru": (
            "Похоже, в номере есть ошибка 🤔\n"
            "Пожалуйста, введите номер в формате +КОД_СТРАНЫ и только цифры.\n"
            "Например: +45 12345678 или +380 991234567."
        ),
    },
    "ask_city": {
        "uk": "З якого Ви міста? 🏙",
        "ru": "Из какого Вы города? 🏙",
    },
    "ask_field": {
        "uk": "У якій сфері Ви плануєте або хотіли б працювати? 👇",
        "ru": "В какой сфере Вы планируете или хотели бы работать? 👇",
    },
    "ask_experience": {
        "uk": "Чи є у Вас досвід у цій сфері? 🙂",
        "ru": "Есть ли у Вас опыт в этой сфере? 🙂",
    },
    "choose_button": {
        "uk": "Будь ласка, скористайтеся кнопками нижче 👇",
        "ru": "Пожалуйста, используйте кнопки ниже 👇",
    },
    "final": {
        "uk": (
            "Дякуємо Вам за реєстрацію! 😊\n\n"
            "Ми зв'яжемося з Вами у березні, перед запуском школи, "
            "або раніше — якщо строки зміняться.\n\n"
            "Якщо Ваша інформація до того часу зміниться, Ви можете пройти "
            "реєстрацію ще раз, надіславши /start."
        ),
        "ru": (
            "Благодарим Вас за регистрацию! 😊\n\n"
            "Мы свяжемся с Вами в марте, перед запуском школы, "
            "или раньше — если сроки изменятся.\n\n"
            "Если Ваша информация к тому моменту изменится, Вы можете пройти "
            "регистрацию ещё раз, отправив /start."
        ),
    },
}

LANG_BUTTONS = [["Українська"], ["Русский"]]

START_BUTTONS = {
    "uk": [["Почати"]],
    "ru": [["Начать"]],
}

POLICY_BUTTONS = {
    "uk": [["Погоджуюсь"], ["Не погоджуюсь"]],
    "ru": [["Согласен"], ["Не согласен"]],
}

PHONE_BUTTONS = {
    "uk": [
        [KeyboardButton("Надіслати номер з Telegram", request_contact=True)],
        ["Ввести номер вручну"],
    ],
    "ru": [
        [KeyboardButton("Отправить номер из Telegram", request_contact=True)],
        ["Ввести номер вручную"],
    ],
}

FIELD_BUTTONS = {
    "uk": [
        ["Клінінг"],
        ["Ресторанний бізнес"],
        ["Бʼюті / краса"],
        ["Інше"],
    ],
    "ru": [
        ["Клининг"],
        ["Ресторанный бизнес"],
        ["Бьюти / красота"],
        ["Другое"],
    ],
}

EXP_BUTTONS = {
    "uk": [
        ["Так, є"],
        ["Трохи"],
        ["Ні, починаю з нуля"],
    ],
    "ru": [
        ["Да, есть"],
        ["Немного"],
        ["Нет, начинаю с нуля"],
    ],
}

PHONE_REGEX = re.compile(r"^(\+45\d{8}|\+380\d{9})$")


def get_lang(context: CallbackContext) -> str:
    return context.user_data.get("lang", "uk")


def map_segment(experience: str, lang: str) -> str:
    uk_map = {
        "Так, є": "есть опыт",
        "Трохи": "немного опыта",
        "Ні, починаю з нуля": "начинаю с нуля",
    }
    ru_map = {
        "Да, есть": "есть опыт",
        "Немного": "немного опыта",
        "Нет, начинаю с нуля": "начинаю с нуля",
    }
    if lang == "uk":
        return uk_map.get(experience, "")
    return ru_map.get(experience, "")


def normalize_phone(raw: str) -> str:
    s = raw.replace(" ", "")
    if not s.startswith("+"):
        s = "+" + "".join(ch for ch in s if ch.isdigit())
    else:
        s = "+" + "".join(ch for ch in s[1:] if ch.isdigit())
    return s


# ---------------- ОБРАБОТЧИКИ ----------------


def start(update: Update, context: CallbackContext) -> int:
    """Команда /start или текст 'Старт' / 'Начать' — выбор языка."""
    context.user_data.clear()
    kb = ReplyKeyboardMarkup(LANG_BUTTONS, resize_keyboard=True, one_time_keyboard=True)
    update.message.reply_text(
        TEXTS["lang_choose"]["uk"], reply_markup=kb
    )
    return LANGUAGE


def language_handler(update: Update, context: CallbackContext) -> int:
    text = (update.message.text or "").strip()
    if text == "Українська":
        lang = "uk"
    elif text == "Русский":
        lang = "ru"
    else:
        kb = ReplyKeyboardMarkup(LANG_BUTTONS, resize_keyboard=True, one_time_keyboard=True)
        update.message.reply_text(TEXTS["lang_choose"]["uk"], reply_markup=kb)
        return LANGUAGE

    context.user_data["lang"] = lang

    kb = ReplyKeyboardMarkup(
        START_BUTTONS[lang], resize_keyboard=True, one_time_keyboard=True
    )
    update.message.reply_text(TEXTS["welcome"][lang], reply_markup=kb)
    return CONSENT


def consent_handler(update: Update, context: CallbackContext) -> int:
    lang = get_lang(context)
    text = (update.message.text or "").strip()

    start_text = "Почати" if lang == "uk" else "Начать"

    if text != start_text:
        kb = ReplyKeyboardMarkup(
            START_BUTTONS[lang], resize_keyboard=True, one_time_keyboard=True
        )
        update.message.reply_text(TEXTS["welcome"][lang], reply_markup=kb)
        return CONSENT

    kb = ReplyKeyboardMarkup(
        POLICY_BUTTONS[lang], resize_keyboard=True, one_time_keyboard=True
    )
    update.message.reply_text(
        TEXTS["policy"][lang],
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
        disable_web_page_preview=True,
    )
    return NAME


def name_handler(update: Update, context: CallbackContext) -> int:
    lang = get_lang(context)
    text = (update.message.text or "").strip()

    agree = "Погоджуюсь" if lang == "uk" else "Согласен"
    disagree = "Не погоджуюсь" if lang == "uk" else "Не согласен"

    if text == disagree:
        update.message.reply_text(
            TEXTS["no_consent"][lang], reply_markup=ReplyKeyboardRemove()
        )
        context.user_data.clear()
        return ConversationHandler.END

    if text == agree:
        update.message.reply_text(
            TEXTS["ask_name"][lang],
            reply_markup=ReplyKeyboardRemove(),
        )
        return NAME

    # считаем, что это уже введённое имя
    if not text:
        update.message.reply_text(TEXTS["ask_name"][lang])
        return NAME

    context.user_data["name"] = text

    kb = ReplyKeyboardMarkup(
        PHONE_BUTTONS[lang], resize_keyboard=True, one_time_keyboard=True
    )
    update.message.reply_text(
        TEXTS["ask_phone_method"][lang],
        reply_markup=kb,
    )
    return PHONE_METHOD


def phone_method_handler(update: Update, context: CallbackContext) -> int:
    lang = get_lang(context)
    msg = update.message

    if msg.contact:
        phone = msg.contact.phone_number
        context.user_data["phone"] = normalize_phone(phone)
        update.message.reply_text(
            TEXTS["ask_city"][lang], reply_markup=ReplyKeyboardRemove()
        )
        return CITY

    text = (msg.text or "").strip()

    manual = "Ввести номер вручну" if lang == "uk" else "Ввести номер вручную"
    send = (
        "Надіслати номер з Telegram"
        if lang == "uk"
        else "Отправить номер из Telegram"
    )

    if text == manual:
        update.message.reply_text(
            TEXTS["ask_phone_manual"][lang],
            reply_markup=ReplyKeyboardRemove(),
        )
        return PHONE_MANUAL

    if text == send:
        # нажали кнопку, но не отправили контакт
        kb = ReplyKeyboardMarkup(
            PHONE_BUTTONS[lang], resize_keyboard=True, one_time_keyboard=True
        )
        update.message.reply_text(TEXTS["choose_button"][lang], reply_markup=kb)
        return PHONE_METHOD

    # любой другой текст
    kb = ReplyKeyboardMarkup(
        PHONE_BUTTONS[lang], resize_keyboard=True, one_time_keyboard=True
    )
    update.message.reply_text(TEXTS["choose_button"][lang], reply_markup=kb)
    return PHONE_METHOD


def phone_manual_handler(update: Update, context: CallbackContext) -> int:
    lang = get_lang(context)
    raw = (update.message.text or "").strip()
    phone_clean = normalize_phone(raw)

    if not PHONE_REGEX.match(phone_clean):
        update.message.reply_text(TEXTS["phone_invalid"][lang])
        return PHONE_MANUAL

    context.user_data["phone"] = phone_clean
    update.message.reply_text(TEXTS["ask_city"][lang])
    return CITY


def city_handler(update: Update, context: CallbackContext) -> int:
    lang = get_lang(context)
    city = (update.message.text or "").strip()
    if not city:
        update.message.reply_text(TEXTS["ask_city"][lang])
        return CITY

    context.user_data["city"] = city

    kb = ReplyKeyboardMarkup(
        FIELD_BUTTONS[lang], resize_keyboard=True, one_time_keyboard=True
    )
    update.message.reply_text(TEXTS["ask_field"][lang], reply_markup=kb)
    return FIELD


def field_handler(update: Update, context: CallbackContext) -> int:
    lang = get_lang(context)
    text = (update.message.text or "").strip()

    allowed_rows = FIELD_BUTTONS[lang]
    allowed = [item for row in allowed_rows for item in row]

    if text not in allowed:
        kb = ReplyKeyboardMarkup(
            FIELD_BUTTONS[lang], resize_keyboard=True, one_time_keyboard=True
        )
        update.message.reply_text(TEXTS["choose_button"][lang], reply_markup=kb)
        return FIELD

    context.user_data["field"] = text

    kb = ReplyKeyboardMarkup(
        EXP_BUTTONS[lang], resize_keyboard=True, one_time_keyboard=True
    )
    update.message.reply_text(TEXTS["ask_experience"][lang], reply_markup=kb)
    return EXPERIENCE


def experience_handler(update: Update, context: CallbackContext) -> int:
    lang = get_lang(context)
    text = (update.message.text or "").strip()

    allowed_rows = EXP_BUTTONS[lang]
    allowed = [item for row in allowed_rows for item in row]

    if text not in allowed:
        kb = ReplyKeyboardMarkup(
            EXP_BUTTONS[lang], resize_keyboard=True, one_time_keyboard=True
        )
        update.message.reply_text(TEXTS["choose_button"][lang], reply_markup=kb)
        return EXPERIENCE

    context.user_data["experience"] = text

    # ---------------- ЗАПИС В ТАБЛИЦЮ ----------------
    user = update.effective_user
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    user_id = user.id if user else ""
    username = user.username or "" if user else ""
    first_name = user.first_name or "" if user else ""

    segment = map_segment(text, lang)
    name = context.user_data.get("name", "")
    phone = context.user_data.get("phone", "")
    city = context.user_data.get("city", "")
    field = context.user_data.get("field", "")

    row = [
        timestamp,   # A timestamp
        user_id,     # B user_id
        username,    # C username
        first_name,  # D first_name
        segment,     # E segment
        name,        # F name
        phone,       # G phone
        city,        # H city
        field,       # I field
        text,        # J experience (кнопка як є)
        "telegram",  # K source
    ]

    try:
        sheet.append_row(row, value_input_option="USER_ENTERED")
    except Exception as e:
        logger.exception(f"Помилка запису в Google Sheets: {e}")

    # фінальне повідомлення
    update.message.reply_text(
        TEXTS["final"][lang],
        reply_markup=ReplyKeyboardRemove(),
    )

    context.user_data.clear()
    return ConversationHandler.END


def cancel(update: Update, context: CallbackContext) -> int:
    lang = get_lang(context)
    if lang == "uk":
        update.message.reply_text(
            "Реєстрацію скасовано. Якщо захочете почати знову — надішліть /start.",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        update.message.reply_text(
            "Регистрация отменена. Если захотите начать снова — отправьте /start.",
            reply_markup=ReplyKeyboardRemove(),
        )
    context.user_data.clear()
    return ConversationHandler.END


# ---------------- MAIN ----------------


def main():
    bot = Bot(token=BOT_TOKEN)
    updater = Updater(bot=bot, use_context=True)
    dp = updater.dispatcher

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            # чтобы кнопка "Старт"/"Начать" тоже перезапускала бота
            MessageHandler(
                Filters.regex(r"^(Старт|Старт )$") | Filters.regex(r"^(Начать|Начать )$"),
                start,
            ),
        ],
        states={
            LANGUAGE: [MessageHandler(Filters.text & ~Filters.command, language_handler)],
            CONSENT: [MessageHandler(Filters.text & ~Filters.command, consent_handler)],
            NAME: [MessageHandler(Filters.text & ~Filters.command, name_handler)],
            PHONE_METHOD: [
                MessageHandler(
                    Filters.contact | (Filters.text & ~Filters.command),
                    phone_method_handler,
                )
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

    dp.add_handler(conv)

    logger.info("Bot is starting...")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()

