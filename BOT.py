from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)
import requests
import os
import asyncio
import json
import time
import logging

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DEEPL_API_KEY = "737c3530-bd62-499e-b8e3-c7e014b9bd27:fx"
BOT_TOKEN = "7768654352:AAF2xXvEySl-_Uet5KuYQIkNucUxfQyzMyo"
ADMIN_IDS = [5356793174, 839685195]  # адміни бота
MAIN_GROUP_ID = -1002847113092      # основна група для алярму

user_lang = {}  # user_id -> lang_code
user_ids = set()  # всі юзери
group_members = {}  # {chat_id: {user_id1, user_id2, ...}}
last_alarm_time = {}  # {chat_id: timestamp} - антиспам

GROUPS_FILE = "group_members.json"

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

def save_groups():
    """Зберігає group_members в файл"""
    data = {str(k): list(v) for k, v in group_members.items()}
    with open(GROUPS_FILE, "w") as f:
        json.dump(data, f)

def load_groups():
    """Завантажує group_members з файлу"""
    global group_members
    try:
        with open(GROUPS_FILE, "r") as f:
            data = json.load(f)
            group_members = {int(k): set(v) for k, v in data.items()}
    except FileNotFoundError:
        group_members = {}

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
    user_id = update.effective_user.id
    is_admin = "✅ ТАК" if user_id in ADMIN_IDS else "❌ НІ"
    await update.message.reply_text(
        f"👋 Обери мову перекладу\n\n"
        f"🆔 Твій ID: `{user_id}`\n"
        f"👑 Адмін: {is_admin}",
        reply_markup=lang_keyboard(),
        parse_mode="Markdown"
    )

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

async def track_group_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Відслідковує хто пише в групі"""
    if update.effective_chat.type in ["group", "supergroup"]:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        if chat_id not in group_members:
            group_members[chat_id] = set()
        
        group_members[chat_id].add(user_id)
        user_ids.add(user_id)
        save_groups()

async def setup_alarm_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /setalarm - створює закріплене повідомлення з кнопкою.

    Працює:
      - у приваті з ботом: тоді бот ставить кнопку в MAIN_GROUP_ID
      - у групі: тоді ставить кнопку в цю групу
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    logger.info(f"🔔 /setalarm від user_id={user_id} в chat_id={chat_id}, type={chat_type}")

    # Тільки адмін бота
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Тільки адмін може встановити")
        logger.warning(f"⛔ Неадмін {user_id} спробував встановити алярм. ADMIN_IDS={ADMIN_IDS}")
        return

    # Куди відправляти кнопку
    if chat_type == "private":
        target_chat_id = MAIN_GROUP_ID
        logger.info(f"🎯 Ставитимемо кнопку в основну групу {MAIN_GROUP_ID}")
    elif chat_type in ["group", "supergroup"]:
        target_chat_id = chat_id
        logger.info(f"🎯 Ставитимемо кнопку в поточну групу {chat_id}")
    else:
        await update.message.reply_text("❌ Працює тільки в приваті з ботом або в групі")
        logger.warning(f"❌ /setalarm з непідтримуваного типу чату: {chat_type}")
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🍆 Смикнути за пісюн", callback_data="alarm_pull")
    ]])

    # Відправляємо з локальним файлом у target_chat_id
    try:
        with open("alarm_button.jpg", "rb") as photo:
            msg = await context.bot.send_photo(
                chat_id=target_chat_id,
                photo=photo,
                caption="**Смикнути за пісюн 🍆**\n\n"
                        "Натисни якщо треба НЕГАЙНО зібрати всіх.\n"
                        "Всі юзери отримають алярм в приват.",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
    except FileNotFoundError:
        # Якщо файл не знайдено - без картинки
        msg = await context.bot.send_message(
            chat_id=target_chat_id,
            text="**Смикнути за пісюн 🍆**\n\n"
                 "Натисни якщо треба НЕГАЙНО зібрати всіх.\n"
                 "Всі юзери отримають алярм в приват.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    # Закріплюємо в групі
    try:
        await context.bot.pin_chat_message(
            chat_id=target_chat_id,
            message_id=msg.message_id,
            disable_notification=True
        )
        # Відповідь там, де адмін викликав команду
        await update.message.reply_text("✅ Кнопку встановлено і закріплено в групі")
    except Exception as e:
        logger.warning(f"⚠️ Не вдалось закріпити повідомлення: {e}")
        await update.message.reply_text(
            "⚠️ Кнопку створено, але не вдалось закріпити.\n"
            "Перевір, що бот має права адміна в цій групі."
        )

async def handle_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка натискання на кнопку алярму"""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    user = query.from_user
    logger.info(f"🚨 АЛЯРМ! Натиснув {user.id} ({user.first_name}) в групі {chat_id}")
    
    # Антиспам: не частіше ніж раз на 60 секунд
    now = time.time()
    if chat_id in last_alarm_time:
        if now - last_alarm_time[chat_id] < 60:
            remaining = int(60 - (now - last_alarm_time[chat_id]))
            logger.info(f"⏳ Антиспам: {remaining} секунд залишилось")
            await query.answer(
                f"⏳ Зачекай {remaining} сек перед наступним алярмом", 
                show_alert=True
            )
            return
    
    last_alarm_time[chat_id] = now
    
    # Дістаємо членів цієї групи
    members = group_members.get(chat_id, set())
    logger.info(f"👥 Знайдено {len(members)} учасників групи")
    
    if not members:
        await query.answer(
            "❌ Ще ніхто не писав в групі.\nПочніть спілкуватись!", 
            show_alert=True
        )
        return
    
    # Повідомлення в групу
    await context.bot.send_message(
        chat_id,
        f"🚨 **АЛЯРМ!** 🚨\n\n"
        f"{user.mention_html()} смикнув за пісюн! 🍆\n"
        f"Викликано {len(members)} людей!",
        parse_mode="HTML"
    )
    
    # Слати тільки членам цієї групи
    group_name = query.message.chat.title or "група"
    success = 0
    failed = 0
    
    logger.info(f"📨 Починаємо розсилку алярму в {len(members)} учасників...")
    for uid in members:
        # Не слати тому хто натиснув
        if uid == user.id:
            continue
            
        try:
            await context.bot.send_message(
                uid,
                f"🚨 **ALARM!** 🚨\n\n"
                f"Зайди в групу **{group_name}** ЗАРАЗ!\n"
                f"Тебе викликав: {user.first_name}",
                parse_mode="Markdown"
            )
            success += 1
        except Exception as e:
            failed += 1
    
    logger.info(f"✅ Перша хвиля: успішно={success}, помилки={failed}")
    
    # Чекаємо 10 секунд
    await asyncio.sleep(10)
    logger.info(f"🔁 Відправляємо другу хвилю...")
    
    # Друга хвиля
    for uid in members:
        if uid == user.id:
            continue
        try:
            await context.bot.send_message(
                uid,
                f"🔔 **ПОВТОР АЛЯРМУ** 🔔\n\n"
                f"Серйозно, зайди в **{group_name}**!",
                parse_mode="Markdown"
            )
        except:
            pass
    
    # Звіт
    await context.bot.send_message(
        chat_id,
        f"✅ Результат розсилки:\n"
        f"📨 Успішно: {success}\n"
        f"❌ Не доставлено: {failed}\n"
        f"🔁 Повтор відправлено через 10 сек"
    )

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
    logger.info("🚀 Бот запускається...")
    
    load_groups()  # завантажуємо збережені групи
    logger.info(f"📋 Завантажено {len(group_members)} груп з {sum(len(m) for m in group_members.values())} учасників")
    
    app = Application.builder().token(BOT_TOKEN).build()
    logger.info("✅ Application створено")
    
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
    logger.info("📝 Базові хендлери додано")
    
    # НОВІ ХЕНДЛЕРИ ДЛЯ АЛЯРМУ
    app.add_handler(CommandHandler("setalarm", setup_alarm_button))
    app.add_handler(CallbackQueryHandler(handle_alarm, pattern="^alarm_pull$"))
    logger.info("🔔 Хендлери алярму додано")
    
    # Трекінг має бути ОСТАННІМ
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.ALL, 
        track_group_member
    ))
    logger.info("👥 Трекінг учасників груп активовано")
    
    logger.info("🏃 Запускаємо polling...")
    app.run_polling()

if __name__ == "__main__":
    main()