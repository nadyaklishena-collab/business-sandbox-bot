import logging
import os
import json
from datetime import datetime

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
    ContextTypes,
    ConversationHandler,
    filters,
)

import gspread
from google.oauth2.service_account import Credentials


# ---------------- ЛОГИ ----------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ---------------- СТАНИ ----------------

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


# ---------------- ENV ----------------

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Registrations")
CREDS_JSON = os.getenv("CREDS_JSON")

POLICY_URL = (
    "https://docs.google.com/document/d/1zeC9FBAj3XRQ0PwPcIRZJ5CSQnTh2AjH8pvB599RMO8/edit"
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан")
if not SPREADSHEET_ID:
    raise RuntimeError("SPREADSHEET_ID не задан")
if not CREDS_JSON:
    raise RuntimeError("CREDS_JSON не задан")


# ---------------- GOOGLE SHEETS ----------------

def get_sheet():
    creds_dict = json.loads(CREDS_JSON)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials = Credentials.from_service_account_info(
        creds_dict,
        scopes=scopes,
    )

    client = gspread.authorize(credentials)
    return client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)


sheet = get_sheet()


def append_row(data: dict):
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


# ---------------- УТИЛІТИ ----------------

def clean_text(text: str) -> str:
    return (text or "").strip()


def is_ua(lang: str) -> bool:
    return lang == "ua"


# ---------------- ОБРОБНИКИ ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    kb = [["Старт"]]
    reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        "Привіт! 👋\n\nЩоб почати — натисніть «Старт».",
        reply_markup=reply_markup,
    )

    return WAIT_START


async def wait_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if clean_text(update.message.text) != "Старт":
        await update.message.reply_text("Будь ласка, натисніть «Старт».")
        return WAIT_START

    kb = [["Погоджуюсь"], ["Не погоджуюсь"]]
    reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        f'Повна версія політики: <a href="{POLICY_URL}">прочитати тут</a>',
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=reply_markup,
    )

    return POLICY


async def policy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = clean_text(update.message.text)

    if text == "Погоджуюсь":
        kb = [["🇺🇦 Українська"], ["🇷🇺 Русский"]]
        await update.message.reply_text(
            "Оберіть мову:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True),
        )
        return LANGUAGE

    if text == "Не погоджуюсь":
        await update.message.reply_text(
            "Без згоди ми не можемо продовжити.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    return POLICY


async def language_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = clean_text(update.message.text)

    if text == "🇺🇦 Українська":
        context.user_data["lang"] = "ua"
    elif text == "🇷🇺 Русский":
        context.user_data["lang"] = "ru"
    else:
        return LANGUAGE

    user = update.effective_user
    context.user_data["user_id"] = user.id
    context.user_data["username"] = user.username or ""
    context.user_data["first_name"] = user.first_name or ""

    await update.message.reply_text(
        "Як Вас звати?",
        reply_markup=ReplyKeyboardRemove(),
    )

    return NAME


async def name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = clean_text(update.message.text)

    share_btn = KeyboardButton("📱 Поділитися контактом", request_contact=True)
    manual_btn = KeyboardButton("📞 Ввести номер вручну")

    await update.message.reply_text(
        "Поділіться телефоном:",
        reply_markup=ReplyKeyboardMarkup(
            [[share_btn], [manual_btn]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )

    return PHONE


async def phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        context.user_data["phone"] = update.message.contact.phone_number
    else:
        context.user_data["phone"] = clean_text(update.message.text)

    await update.message.reply_text(
        "В якому місті Ви проживаєте?",
        reply_markup=ReplyKeyboardRemove(),
    )

    return CITY


async def city_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["city"] = clean_text(update.message.text)

    kb = [["Б'юті", "Ресторанний бізнес"], ["Клінінг", "Інше"]]

    await update.message.reply_text(
        "Оберіть сферу:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True),
    )

    return FIELD


async def field_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["field"] = clean_text(update.message.text)

    kb = [["Так", "Ні"]]

    await update.message.reply_text(
        "Чи є у Вас досвід?",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True),
    )

    return EXPERIENCE


async def experience_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["experience"] = clean_text(update.message.text)

    append_row(context.user_data)

    await update.message.reply_text(
        "Дякуємо за реєстрацію 💛",
        reply_markup=ReplyKeyboardRemove(),
    )

    context.user_data.clear()
    return ConversationHandler.END


# ---------------- MAIN ----------------

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
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, city_handler)],
            FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, field_handler)],
            EXPERIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, experience_handler)],
        },
        fallbacks=[],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)

    logger.info("Bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
