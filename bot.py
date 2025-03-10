import telebot
import sqlite3
import shutil
import os
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "7903638080:AAFD-L6OhzkqbLeXi03WEguSBUYnCM0APXs"
ADMIN_ID = 1338207670
CHANNEL_USERNAME = "@moowies1000"

bot = telebot.TeleBot(TOKEN)

DB_NAME = "series.db"
BACKUP_FILE = "backup_series.db"

EPISODES_PER_PAGE = 10  # عدد الحلقات في كل صفحة

bot_info = bot.get_me()
BOT_USERNAME = bot_info.username

def create_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_name TEXT,
            episode_name TEXT,
            file_id TEXT UNIQUE
        )
    """)
    conn.commit()
    conn.close()

create_db()

def restore_backup():
    if os.path.exists(BACKUP_FILE):
        shutil.copy(BACKUP_FILE, DB_NAME)
        print("✅ تم استرجاع النسخة الاحتياطية!")

restore_backup()
@bot.message_handler(content_types=['document'])
def receive_backup(message):
    if message.chat.id == ADMIN_ID:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with open(BACKUP_FILE, "wb") as f:
            f.write(downloaded_file)

        shutil.copy(BACKUP_FILE, DB_NAME)

        # ✅ إرسال تأكيد للمشرف بعد نجاح الاسترجاع
        bot.send_message(ADMIN_ID, "✅ تم استرجاع النسخة الاحتياطية بنجاح!")
def backup_database():
    shutil.copy(DB_NAME, BACKUP_FILE)
    print("✅ تم إنشاء نسخة احتياطية!")

@bot.channel_post_handler(content_types=['video', 'document'])
def save_episode_from_channel(message):
    if message.caption and message.sender_chat and message.sender_chat.username == CHANNEL_USERNAME.lstrip("@"):
        file_id = message.video.file_id if message.video else message.document.file_id
        series_name = message.caption.strip()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM episodes WHERE file_id=?", (file_id,))
        existing = cursor.fetchone()

        if not existing:
            cursor.execute("INSERT INTO episodes (series_name, episode_name, file_id) VALUES (?, ?, ?)",
                           (series_name, message.caption, file_id))
            conn.commit()
            backup_database()
            bot.send_message(ADMIN_ID, f"✅ تم حفظ **{series_name}** من القناة!")

        conn.close()

@bot.message_handler(func=lambda message: message.chat.type in ["group", "supergroup"])
def show_episodes(message):
    series_name = message.text.strip()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, episode_name FROM episodes WHERE series_name LIKE ? ORDER BY episode_name DESC",
                   (f"%{series_name}%",))
    episodes = cursor.fetchall()
    conn.close()

    if episodes:
        send_episodes_list(message.chat.id, message.message_id, series_name, episodes, 0)
    else:
        bot.send_message(message.chat.id, "✅ تم إرسال طلبك، وسوف يتوفر قريبًا!")
        bot.send_message(ADMIN_ID, f"📌 **طلب جديد:**\n🔎 {series_name}\n⚡ مطلوب توفيره قريبًا!")

def send_episodes_list(chat_id, message_id, series_name, episodes, page):
    start_idx = page * EPISODES_PER_PAGE
    end_idx = start_idx + EPISODES_PER_PAGE
    current_episodes = episodes[start_idx:end_idx]

    markup = InlineKeyboardMarkup()
    for episode_id, episode_name in current_episodes:
        episode_link = f"https://t.me/{BOT_USERNAME}?start={episode_id}"
        markup.add(InlineKeyboardButton(text=episode_name, url=episode_link))

    navigation_buttons = []
    if start_idx > 0:
        navigation_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"prev_{series_name}_{page-1}"))
    if end_idx < len(episodes):
        navigation_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"next_{series_name}_{page+1}"))

    if navigation_buttons:
        markup.add(*navigation_buttons)

    try:
        bot.edit_message_reply_markup(chat_id, message_id, reply_markup=markup)
    except:
        bot.send_message(chat_id, "🎬 اختر الحلقة:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith(("next_", "prev_")))
def navigate_pages(call):
    data = call.data.split("_")
    action, series_name, page = data[0], data[1], int(data[2])

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, episode_name FROM episodes WHERE series_name LIKE ? ORDER BY episode_name DESC",
                   (f"%{series_name}%",))
    episodes = cursor.fetchall()
    conn.close()

    if episodes:
        send_episodes_list(call.message.chat.id, call.message.message_id, series_name, episodes, page)

@bot.message_handler(commands=['start'])
def send_episode_private(message):
    args = message.text.split()
    if len(args) > 1:
        episode_id = args[1]
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT file_id, episode_name FROM episodes WHERE id=?", (episode_id,))
        episode = cursor.fetchone()
        conn.close()

        if episode:
            file_id, episode_name = episode
            bot.send_video(message.chat.id, file_id, caption=f"🎬 **{episode_name}**")
        else:
            bot.send_message(message.chat.id, "❌ الحلقة غير موجودة أو تم حذفها.")
    else:
        bot.send_message(message.chat.id, "👋 مرحبًا! استخدم البوت لاختيار الحلقات.")

@bot.message_handler(commands=['edit'])
def edit_episode(message):
    if message.chat.id == ADMIN_ID:
        bot.send_message(ADMIN_ID, "🔹 أرسل اسم الحلقة التي تريد تعديلها:")
        bot.register_next_step_handler(message, ask_for_new_name)

def ask_for_new_name(message):
    episode_name = message.text.strip()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM episodes WHERE episode_name=?", (episode_name,))
    episode = cursor.fetchone()
    conn.close()

    if episode:
        bot.send_message(ADMIN_ID, f"🔹 أرسل الاسم الجديد للحلقة **{episode_name}**:")
        bot.register_next_step_handler(message, save_new_name, episode[0])
    else:
        bot.send_message(ADMIN_ID, "❌ الحلقة غير موجودة.")

def save_new_name(message, episode_id):
    new_name = message.text.strip()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE episodes SET episode_name=? WHERE id=?", (new_name, episode_id))
    conn.commit()
    conn.close()
    bot.send_message(ADMIN_ID, f"✅ تم تعديل اسم الحلقة إلى: **{new_name}**")

@bot.message_handler(commands=['delete'])
def delete_episode(message):
    if message.chat.id == ADMIN_ID:
        bot.send_message(ADMIN_ID, "🔹 أرسل اسم الحلقة التي تريد حذفها:")
        bot.register_next_step_handler(message, delete_episode_by_name)

def delete_episode_by_name(message):
    episode_name = message.text.strip()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM episodes WHERE episode_name=?", (episode_name,))
    episode = cursor.fetchone()
    conn.close()

    if episode:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM episodes WHERE id=?", (episode[0],))
        conn.commit()
        conn.close()
        bot.send_message(ADMIN_ID, f"✅ تم حذف الحلقة: **{episode_name}**")
    else:
        bot.send_message(ADMIN_ID, "❌ الحلقة غير موجودة.")

@bot.message_handler(commands=['backup'])
def send_backup(message):
    if message.chat.id == ADMIN_ID:
        if os.path.exists(BACKUP_FILE):
            with open(BACKUP_FILE, "rb") as f:
                bot.send_document(ADMIN_ID, f, caption="📂 النسخة الاحتياطية لقاعدة البيانات")
        else:
            bot.send_message(ADMIN_ID, "❌ لا توجد نسخة احتياطية بعد!")

bot.polling(none_stop=True)