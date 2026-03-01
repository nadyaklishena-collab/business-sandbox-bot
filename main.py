import json
import logging
import os
from datetime import datetime

from dotenv import load_dotenv

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

import gspread
from oauth2client.service_account import ServiceAccountCredentials


# ---- ЛОГИ ----
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---- СТАНИ ----
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

# ---- ENV ----
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Registrations")

# JSON с ключами сервис-аккаунта (строкой) из Render Env
CREDS_JSON = os.getenv("CREDS_JSON")

POLICY_URL = "https://docs.google.com/document/d/1zeC9FBAj3XRQ0PwPcIRZJ5CSQnTh2AjH8pvB599RMO8/edit"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN / TELEGRAM_BOT_TOKEN не знайдено в env")
if not SPREADSHEET_ID:
    raise RuntimeError("SPREADSHEET_ID не знайдено в env")
if not CREDS_JSON:
    raise RuntimeError("CREDS_JSON не знайдено в env (має бути JSON-рядок ключа)")


# ---- GOOGLE SHEETS ----
def init_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = json.loads(CREDS_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
    return sheet


sheet = init_sheet()


def append_row(data: dict):
    try:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        row = [
            timestamp,
            data.get("user_id", ""),
            data.get("username", ""),
            data.get("first_name", ""),
            data.get("lang", ""),
            data.get("name", ""),
            data.get("phone", ""),
            data.get("city", ""),
            data.get("field", ""),
            data.get("experience", ""),
            "telegram",
        ]
        sheet.append_row(row)
    except Exception as e:
        logger.exception(f"Помилка запису в Google Sheets: {e}")


# ---- ТЕКСТИ ----
WELCOME_UA = (
    "Привіт! 👋\n"
    "Ми запускаємо Business Sandbox — безкоштовну бізнес-школу для українців в Орхусі.\n"
    "(навчання українською або російською мовами)\n\n"
    "Щоб почати — натисніть кнопку «Старт»."
)

POLICY_UA = (
    "Перш ніж ми почнемо 😊\n\n"
    "Натискаючи «Почати» та продовжуючи реєстрацію, Ви погоджуєтеся на обробку Ваших "
    "персональних даних (ім’я, телефон, місто, сфера діяльності).\n\n"
    'Повна версія політики та згоди: <a href="{url}">прочитати тут</a>.'
)

LANG_CHOICE = "Будь ласка, оберіть мову спілкування:"
LANG_KB = [["🇺🇦 Українська"], ["🇷🇺 Русский"]]


def is_ua(lang: str) -> bool:
    return lang == "ua"


def clean_text(text: str) -> str:
    return (text or "").strip()


# ---- HANDLERS (ASYNC) ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    kb = [["Старт"]]
    reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(WELCOME_UA, reply_markup=reply_markup)
    return WAIT_START


async def wait_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = clean_text(update.message.text)
    if text != "Старт":
        await update.message.reply_text("Щоб розпочати, натисніть кнопку «Старт».")
        return WAIT_START

    kb = [["Погоджуюсь"], ["Не погоджуюсь"]]
    reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        POLICY_UA.format(url=POLICY_URL),
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )
    return POLICY


async def policy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = clean_text(update.message.text)

    if text == "Погоджуюсь":
        reply_markup = ReplyKeyboardMarkup(LANG_KB, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(LANG_CHOICE, reply_markup=reply_markup)
        return LANGUAGE

    if text == "Не погоджуюсь":
        kb = [["Старт"]]
        reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            "Дякуємо! Без згоди ми не можемо продовжити.\n\n"
            "Якщо передумаєте — натисніть «Старт».",
            reply_markup=reply_markup,
        )
        return WAIT_START

    await update.message.reply_text("Будь ласка, оберіть кнопкою: «Погоджуюсь» або «Не погоджуюсь».")
    return POLICY


async def language_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = clean_text(update.message.text)

    if text == "🇺🇦 Українська":
        context.user_data["lang"] = "ua"
    elif text == "🇷🇺 Русский":
        context.user_data["lang"] = "ru"
    else:
        await update.message.reply_text("Будь ласка, оберіть мову кнопкою.")
        return LANGUAGE

    user = update.effective_user
    if user:
        context.user_data["user_id"] = user.id
        context.user_data["username"] = user.username or ""
        context.user_data["first_name"] = user.first_name or ""

    if is_ua(context.user_data["lang"]):
        await update.message.reply_text("Як Вас звати?", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("Как Вас зовут?", reply_markup=ReplyKeyboardRemove())
    return NAME


async def name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "ua")
    name = clean_text(update.message.text)

    if not name:
        await update.message.reply_text("Введіть ім’я текстом." if is_ua(lang) else "Введите имя текстом.")
        return NAME

    context.user_data["name"] = name

    if is_ua(lang):
        share_btn = KeyboardButton("📱 Поділитися контактом", request_contact=True)
        manual_btn = KeyboardButton("📞 Ввести номер вручну")
        text = "Поділіться номером телефону або введіть вручну."
    else:
        share_btn = KeyboardButton("📱 Поделиться контактом", request_contact=True)
        manual_btn = KeyboardButton("📞 Ввести номер вручную")
        text = "Поделитесь номером телефона или введите вручную."

    reply_markup = ReplyKeyboardMarkup([[share_btn], [manual_btn]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(text, reply_markup=reply_markup)
    return PHONE


async def phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "ua")

    if update.message.contact:
        context.user_data["phone"] = update.message.contact.phone_number
        await update.message.reply_text(
            "В якому місті Ви зараз проживаєте?" if is_ua(lang) else "В каком городе Вы сейчас живёте?",
            reply_markup=ReplyKeyboardRemove(),
        )
        return CITY

    text = clean_text(update.message.text)

    if is_ua(lang) and text == "📞 Ввести номер вручну":
        await update.message.reply_text("Введіть номер у форматі +45 00 00 00 00.", reply_markup=ReplyKeyboardRemove())
        return PHONE_MANUAL

    if not is_ua(lang) and text == "📞 Ввести номер вручную":
        await update.message.reply_text("Введите номер в формате +45 00 00 00 00.", reply_markup=ReplyKeyboardRemove())
        return PHONE_MANUAL

    await update.message.reply_text("Будь ласка, використайте кнопки." if is_ua(lang) else "Пожалуйста, используйте кнопки.")
    return PHONE


async def phone_manual_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "ua")
    phone = clean_text(update.message.text)
    digits = [c for c in phone if c.isdigit()]

    if not phone.startswith("+") or len(digits) < 8:
        await update.message.reply_text(
            "Некоректний формат. Приклад: +45 00 00 00 00" if is_ua(lang)
            else "Неверный формат. Пример: +45 00 00 00 00"
        )
        return PHONE_MANUAL

    context.user_data["phone"] = phone
    await update.message.reply_text(
        "В якому місті Ви зараз проживаєте?" if is_ua(lang) else "В каком городе Вы сейчас живёте?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return CITY


async def city_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "ua")
    city = clean_text(update.message.text)

    if not city:
        await update.message.reply_text("Напишіть місто текстом." if is_ua(lang) else "Напишите город текстом.")
        return CITY

    context.user_data["city"] = city

    if is_ua(lang):
        kb = [["Б'юті", "Ресторанний бізнес"], ["Клінінг", "Інше"]]
        text = "У якій сфері Ви плануєте або хотіли б працювати?"
    else:
        kb = [["Бьюти", "Ресторанный бизнес"], ["Клининг", "Другое"]]
        text = "В какой сфере Вы планируете или хотели бы работать?"

    await update.message.reply_text(text, reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return FIELD


async def field_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "ua")
    field = clean_text(update.message.text)

    if is_ua(lang):
        allowed = ["Б'юті", "Ресторанний бізнес", "Клінінг", "Інше"]
        error_text = "Оберіть сферу кнопкою."
    else:
        allowed = ["Бьюти", "Ресторанный бизнес", "Клининг", "Другое"]
        error_text = "Выберите сферу кнопкой."

    if field not in allowed:
        await update.message.reply_text(error_text)
        return FIELD

    context.user_data["field"] = field

    kb = [["Так", "Ні"]] if is_ua(lang) else [["Да", "Нет"]]
    text = "Чи є у Вас досвід в цій сфері?" if is_ua(lang) else "Есть ли у Вас опыт в этой сфере?"
    await update.message.reply_text(text, reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return EXPERIENCE


async def experience_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get("lang", "ua")
    answer = clean_text(update.message.text)

    if is_ua(lang):
        allowed = ("Так", "Ні")
        error_text = "Оберіть «Так» або «Ні» кнопкою."
    else:
        allowed = ("Да", "Нет")
        error_text = "Выберите «Да» или «Нет» кнопкой."

    if answer not in allowed:
        await update.message.reply_text(error_text)
        return EXPERIENCE

    context.user_data["experience"] = answer
    append_row(context.user_data)

    if is_ua(lang):
        final_text = "Дякуємо за реєстрацію! 💛\n\nМи зв'яжемося з Вами у липні (або раніше, якщо щось зміниться)."
        again_text = "Якщо дані змінились — натисніть /start і пройдіть ще раз."
    else:
        final_text = "Спасибо за регистрацию! 💛\n\nМы свяжемся с Вами в июле (или раньше, если что-то изменится)."
        again_text = "Если данные изменились — нажмите /start и пройдите ещё раз."

    await update.message.reply_text(final_text, reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text(again_text)

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Реєстрацію скасовано. Щоб почати знову — /start.", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAIT_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, wait_start)],
            POLICY: [MessageHandler(filters.TEXT & ~filters.COMMAND, policy_handler)],
            LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, language_handler)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_handler)],
            PHONE: [
                MessageHandler(filters.CONTACT, phone_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, phone_handler),
            ],
            PHONE_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_manual_handler)],
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, city_handler)],
            FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, field_handler)],
            EXPERIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, experience_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    logger.info("Bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
