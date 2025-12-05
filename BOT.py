from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)
import requests
import os

DEEPL_API_KEY = "737c3530-bd62-499e-b8e3-c7e014b9bd27:fx"
BOT_TOKEN = "7768654352:AAF2xXvEySl-_Uet5KuYQIkNucUxfQyzMyo"
ADMIN_IDS = [5356793174]  # заміни на свій Telegram ID

user_lang = {}  # user_id -> lang_code
user_ids = set()  # всі юзери

DEEPL_LANGUAGES = [
    ("English", "en"), ("Ukrainian", "uk"), ("Polish", "pl"), ("German", "de"), ("French", "fr"),
    ("Spanish", "es"), ("Italian", "it"), ("Turkish", "tr"), ("Romanian", "ro"), ("Dutch", "nl"),
    ("Portuguese", "pt"), ("Russian", "ru"), ("Japanese", "ja"), ("Chinese", "zh"), ("Korean", "ko"),
    ("Arabic", "ar"), ("Czech", "cs"), ("Danish", "da"), ("Finnish", "fi"), ("Greek", "el"),
    ("Hebrew", "he"), ("Hindi", "hi"), ("Hungarian", "hu"), ("Indonesian", "id"), ("Malay", "ms"),
    ("Norwegian", "no"), ("Persian", "fa"), ("Slovak", "sk"), ("Swedish", "sv"), ("Thai", "th"),
    ("Vietnamese", "vi"), ("Bulgarian", "bg"), ("Catalan", "ca"), ("Croatian", "hr"), ("Estonian", "et"),
    ("Filipino", "tl"), ("Georgian", "ka"), ("Latvian", "lv"), ("Lithuanian", "lt"), ("Macedonian", "mk"),
    ("Serbian", "sr"), ("Slovenian", "sl"), ("Swahili", "sw"), ("Tagalog", "tl"), ("Urdū", "ur"),
    ("Belarusian", "be"), ("Basque", "eu"), ("Galician", "gl"), ("Icelandic", "is"), ("Irish", "ga")
]

BROADCAST = range(1)

def lang_keyboard():
    rows = []
    for i in range(0, len(DEEPL_LANGUAGES), 2):
        row = []
        for lang in DEEPL_LANGUAGES[i:i + 2]:
            row.append(InlineKeyboardButton(lang[0], callback_data=f"lang_{lang[1]}"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_ids.add(update.effective_user.id)
    await update.message.reply_text("👋 Обери мову перекладу", reply_markup=lang_keyboard())

async def set_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang_code = query.data.split("_")[1]
    user_lang[query.from_user.id] = lang_code
    user_ids.add(query.from_user.id)
    await query.answer()
    await query.edit_message_text(f"✅ Мова встановлена: {lang_code}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌍 Перекласти", callback_data=f"translate_{msg.message_id}")]
    ])
    reply = await context.bot.send_message(
        chat_id=msg.chat_id,
        reply_to_message_id=msg.message_id,
        text="\u2063",
        reply_markup=keyboard
    )
    context.chat_data[f"reply_{msg.message_id}"] = reply.message_id

async def translate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    lang = user_lang.get(user_id)

    if not lang:
        await query.answer("Спочатку вибери мову в /start", show_alert=True)
        await context.bot.send_message(chat_id=user_id, text="Обери мову:", reply_markup=lang_keyboard())
        return

    original_msg = query.message.reply_to_message
    if not original_msg:
        await query.answer("❌ Немає повідомлення для перекладу", show_alert=True)
        return

    text_to_translate = original_msg.text or original_msg.caption
    if not text_to_translate:
        await query.answer("❌ У повідомленні немає тексту", show_alert=True)
        return

    translated = translate_text(text_to_translate, lang)

    if len(translated) > 200:
        await query.answer("📄 Переклад надіслано в приват", show_alert=True)
        await context.bot.send_message(chat_id=user_id, text=f"📄 Повний переклад:\n{translated}")
    else:
        await query.answer("📄 " + translated, show_alert=True)

async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Тільки для адміна")
        return ConversationHandler.END
    await update.message.reply_text("✍️ Введи повідомлення для розсилки:")
    return BROADCAST

async def do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    original_text = update.message.text
    count = 0
    for uid in user_ids:
        lang = user_lang.get(uid, "en")
        translated = translate_text(original_text, lang)
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 {translated}")
            count += 1
        except:
            continue
    await update.message.reply_text(f"✅ Розіслано {count} юзерам")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Розсилку скасовано")
    return ConversationHandler.END

def translate_text(text, target_lang):
    url = "https://api-free.deepl.com/v2/translate"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "auth_key": DEEPL_API_KEY,
        "text": text,
        "target_lang": target_lang.upper()
    }
    response = requests.post(url, headers=headers, data=data)
    return response.json()["translations"][0]["text"]

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", start_broadcast)],
        states={
            BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, do_broadcast)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(broadcast_conv)
    app.add_handler(CallbackQueryHandler(set_lang, pattern="^lang_"))
    app.add_handler(CallbackQueryHandler(translate_callback, pattern="^translate_"))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()