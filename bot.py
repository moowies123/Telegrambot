import telebot
import sqlite3
import shutil
import os
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "7903638080:AAFD-L6OhzkqbLeXi03WEguSBUYnCM0APXs"  # 🔹 ضع التوكن هنا
ADMIN_ID = 1338207670  # 🔹 ضع الـ ID الخاص بك هنا
CHANNEL_USERNAME = "@moowies1000"  # 🔹 ضع يوزر القناة هنا

bot = telebot.TeleBot(TOKEN)

DB_NAME = "series.db"
BACKUP_FILE = "backup_series.db"  # 🔹 ملف النسخة الاحتياطية

bot_info = bot.get_me()
BOT_USERNAME = bot_info.username  # 🔹 اسم المستخدم للبوت

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

        if existing:
            bot.send_message(ADMIN_ID, f"⚠️ الحلقة {series_name} مضافة بالفعل!")
        else:
            cursor.execute("INSERT INTO episodes (series_name, episode_name, file_id) VALUES (?, ?, ?)",
                           (series_name, message.caption, file_id))
            conn.commit()
            conn.close()
            backup_database()
            bot.send_message(ADMIN_ID, f"✅ تم حفظ **{series_name}** من القناة!")

@bot.message_handler(func=lambda message: message.chat.type in ["group", "supergroup"])
def show_episodes(message):
    series_name = message.text.strip()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, episode_name FROM episodes WHERE series_name LIKE ? ORDER BY episode_name ASC",
                   (f"%{series_name}%",))
    episodes = cursor.fetchall()
    conn.close()

    if episodes:
        markup = InlineKeyboardMarkup()
        for episode_id, episode_name in episodes:
            episode_link = f"https://t.me/{BOT_USERNAME}?start={episode_id}"
            markup.add(InlineKeyboardButton(text=episode_name, url=episode_link))

        bot.send_message(message.chat.id, "🎬 اختر الحلقة وسيتم إرسالها لك في الشات الخاص:", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "✅ تم إرسال طلبك، وسوف يتوفر قريبًا!")
        bot.send_message(ADMIN_ID, f"📌 **طلب جديد من المستخدم:**\n\n🔎 **{series_name}**\n\n⚡ مطلوب توفيره قريبًا!")

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
        bot.send_message(ADMIN_ID, "🔹 قول اسم الحلقة اللي عايز تعدلها.")
        bot.register_next_step_handler(message, ask_for_new_name)

def ask_for_new_name(message):
    series_name = message.text.strip()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, episode_name FROM episodes WHERE episode_name=?", (series_name,))
    episode = cursor.fetchone()
    conn.close()

    if episode:
        bot.send_message(ADMIN_ID, f"🔹 الآن قول الاسم الجديد للحلقة {series_name}.")
        bot.register_next_step_handler(message, save_new_name, episode[0])
    else:
        bot.send_message(ADMIN_ID, "❌ الحلقة غير موجودة، حاول مرة أخرى.")

def save_new_name(message, episode_id):
    new_name = message.text.strip()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE episodes SET episode_name=? WHERE id=?", (new_name, episode_id))
    conn.commit()
    conn.close()

    bot.send_message(ADMIN_ID, f"✅ تم تعديل اسم الحلقة إلى: {new_name}")

@bot.message_handler(commands=['delete'])
def delete_episode(message):
    if message.chat.id == ADMIN_ID:
        bot.send_message(ADMIN_ID, "🔹 قول اسم الحلقة اللي عايز تحذفها.")
        bot.register_next_step_handler(message, delete_episode_by_name)

def delete_episode_by_name(message):
    series_name = message.text.strip()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM episodes WHERE episode_name=?", (series_name,))
    episode = cursor.fetchone()
    conn.close()

    if episode:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM episodes WHERE id=?", (episode[0],))
        conn.commit()
        conn.close()
        bot.send_message(ADMIN_ID, f"✅ تم حذف الحلقة: {series_name}")
    else:
        bot.send_message(ADMIN_ID, "❌ الحلقة غير موجودة، حاول مرة أخرى.")

@bot.message_handler(commands=['backup'])
def send_backup(message):
    if message.chat.id == ADMIN_ID:
        if os.path.exists(BACKUP_FILE):
            bot.send_document(ADMIN_ID, open(BACKUP_FILE, "rb"), caption="📂 النسخة الاحتياطية لقاعدة البيانات")
        else:
            bot.send_message(ADMIN_ID, "❌ لا توجد نسخة احتياطية بعد!")

@bot.message_handler(content_types=['document'])
def receive_backup(message):
    if message.chat.id == ADMIN_ID:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with open(BACKUP_FILE, "wb") as f:
            f.write(downloaded_file)

        # استبدال قاعدة البيانات الحالية بالنسخة المستلمة
        shutil.copy(BACKUP_FILE, DB_NAME)
        
        # 🔹 إرسال تأكيد للمشرف
        bot.send_message(ADMIN_ID, "✅ تم استرجاع النسخة الاحتياطية بنجاح!")

bot.polling(none_stop=True)