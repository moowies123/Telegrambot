import urllib.parse
import uuid
import telebot
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import shutil
import re
import os
import yt_dlp
import time
import random
import string
import threading
import html
import hashlib
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from flask import Flask
from rapidfuzz import fuzz
from types import SimpleNamespace
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from google import genai
import json

from dotenv import load_dotenv

load_dotenv()

START_TIME = time.time()

TOKEN = os.environ.get("TOKEN", "")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")

client = genai.Client(
    api_key=os.environ.get("GEMINI_API_KEY", ""),
    http_options={"api_version": "v1"}
)

ADMIN_ID = 1338207670
GROUP_ID = -1003876477799              # جروب القناة الرسمي
RECOMMEND_CHANNEL_ID = -1003709621420  # ID قناة الترشيحات
RECOMMEND_INTERVAL = 600               # 10 دقائق
CONTENT_CHANNEL_ID = -1002360047363    # ID القناة الخاصة بالمحتوى
RECOMMEND_CHANNEL = -1003709621420
PROMO_GROUP_ID = -1003472601279        # الجروب الدعائي

bot = telebot.TeleBot(TOKEN)

# =========================================================
# 🗄️ إعدادات قاعدة البيانات والملفات
# =========================================================
DB_NAME = "series.db"
BACKUP_FILE = "backup_series.db"

backup_conn = sqlite3.connect(
    DB_NAME,
    check_same_thread=False
)

from stats import *
from backup_system import *
from downloader import *

EPISODES_PER_PAGE = 8       # عدد الأزرار الرئيسية
EP_NUMBERS_PER_PAGE = 10    # عدد أرقام الحلقات في الصفحة
MOVIES_PER_PAGE = 10        # عدد الأفلام في الصفحة
MAX_TRANSFERS = 15          # عدد التحويلات
TIME_WINDOW = 60            # خلال كام ثانية
AUTO_BLOCK = True           # False = إنذار بس

# 🧠 تخزين مؤقت لجلسات المستخدمين
user_sessions = {}
series_sessions = {}
search_sessions = {}
confirm_sessions = {}
SERIES_CACHE = {}
CACHE_TTL = 300  # 5 دقائق
MOVIES_CACHE = {}
MOVIES_CACHE_TTL = 300
FAST_SEARCH_CACHE = {}
FAST_SEARCH_TTL = 300
USER_TRANSFERS = {}
BLOCKED_USERS = set()
private_search_mode = {}
LAST_NOTIFIED = {}
NOTIFICATIONS_ENABLED = True
RANGE_SESSIONS = {}
control_actions = {}
SUBS_NOTIFIED = {}
OWNER_USERNAME = "MohamedOwies"
SAVE_LOGS = {}
trend_sessions = {}
BLOCKED_SEARCH_USERS = {}
BATCH_VIDEOS = []
BATCH_TIMER = None
BATCH_WAIT_SECONDS = 5
BATCH_LOCK = threading.Lock()
WAITING_FOR_BATCH_NAME = False
movie_sessions = {}

# 🟢 جلب اسم البوت
try:
    bot_info = bot.get_me()
    BOT_USERNAME = bot_info.username
except Exception:
    BOT_USERNAME = "cimabotbest"


# =========================================================
# 💾 إدارة قاعدة البيانات والـ series_id
# =========================================================

def get_or_create_series_id(series_name: str, media_type: str = "series") -> str:
    """توليد معرف ثابت وفريد لكل مسلسل أو فيلم."""
    base = get_base_series_name(series_name) or str(series_name).strip().lower()
    h = hashlib.md5(base.encode("utf-8")).hexdigest()[:10]
    prefix = "mov_" if media_type == "movie" else "ser_"
    return f"{prefix}{h}"


def create_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            join_date TEXT,
            is_blocked INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id TEXT,
            series_name TEXT,
            episode_name TEXT,
            file_id TEXT UNIQUE,
            quality TEXT,
            media_type TEXT DEFAULT 'series',
            season INTEGER DEFAULT 1,
            episode INTEGER DEFAULT 0,
            release_year TEXT,
            views INTEGER DEFAULT 0,
            added_date TEXT,
            link_id TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id TEXT,
            series_name TEXT,
            media_type TEXT DEFAULT 'series',
            link_id TEXT UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS series_captions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id TEXT,
            series_name TEXT UNIQUE,
            caption TEXT,
            photo_file_id TEXT,
            tmdb_id TEXT,
            poster TEXT,
            rating TEXT,
            genres TEXT,
            country TEXT,
            release_date TEXT,
            actors TEXT,
            director TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            start_date TEXT,
            end_date TEXT,
            plan TEXT DEFAULT 'VIP'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscription_codes (
            code TEXT PRIMARY KEY,
            months INTEGER,
            duration_days INTEGER,
            used INTEGER DEFAULT 0,
            used_by INTEGER,
            used_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            query TEXT,
            search_date TEXT,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            series_id TEXT,
            series_name TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER UNIQUE,
            title TEXT,
            added_date TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backup_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER UNIQUE,
            backup_file TEXT,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movie_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_name TEXT UNIQUE,
            posted_at TEXT
        )
    """)

    # فهارس فائقة السرعة للبحث
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_series_name ON episodes(series_name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_series_id ON episodes(series_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_media_type ON episodes(media_type);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_links_series_name ON links(series_name);")

    conn.commit()
    conn.close()
    print("🟢 Database Ready & Indexed")


def upgrade_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    episode_columns = {
        "series_id": "TEXT",
        "link_id": "TEXT",
        "quality": "TEXT",
        "media_type": "TEXT DEFAULT 'series'",
        "season": "INTEGER DEFAULT 1",
        "episode": "INTEGER DEFAULT 0",
        "release_year": "TEXT",
        "views": "INTEGER DEFAULT 0",
        "added_date": "TEXT"
    }

    for column, column_type in episode_columns.items():
        try:
            cursor.execute(f"ALTER TABLE episodes ADD COLUMN {column} {column_type}")
            print(f"✅ Added {column} to episodes")
        except sqlite3.OperationalError:
            pass

    try:
        cursor.execute("ALTER TABLE links ADD COLUMN series_id TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE links ADD COLUMN media_type TEXT DEFAULT 'series'")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE series_captions ADD COLUMN series_id TEXT")
    except sqlite3.OperationalError:
        pass

    captions_columns = {
        "tmdb_id": "TEXT",
        "poster": "TEXT",
        "rating": "TEXT",
        "genres": "TEXT",
        "country": "TEXT",
        "release_date": "TEXT",
        "actors": "TEXT",
        "director": "TEXT"
    }

    for column, column_type in captions_columns.items():
        try:
            cursor.execute(f"ALTER TABLE series_captions ADD COLUMN {column} {column_type}")
        except sqlite3.OperationalError:
            pass

    sub_code_columns = {
        "duration_days": "INTEGER",
        "used_by": "INTEGER",
        "used_at": "TEXT"
    }

    for column, column_type in sub_code_columns.items():
        try:
            cursor.execute(f"ALTER TABLE subscription_codes ADD COLUMN {column} {column_type}")
        except sqlite3.OperationalError:
            pass

    try:
        cursor.execute("ALTER TABLE search_history ADD COLUMN created_at TEXT")
    except sqlite3.OperationalError:
        pass

    # تحديث وتعبئة series_id للبيانات القديمة
    cursor.execute("SELECT id, series_name, media_type FROM episodes WHERE series_id IS NULL OR series_id = ''")
    to_update = cursor.fetchall()
    for row_id, s_name, m_type in to_update:
        sid = get_or_create_series_id(s_name or "unknown", m_type or "series")
        cursor.execute("UPDATE episodes SET series_id = ? WHERE id = ?", (sid, row_id))

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_series_name ON episodes(series_name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_series_id ON episodes(series_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodes_media_type ON episodes(media_type);")

    conn.commit()
    conn.close()
    print("🟢 Database upgraded and series_id synced successfully")


def link_old_series():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT series_name, link_id FROM links")
    links = cursor.fetchall()

    for series_name, link_id in links:
        cursor.execute(
            "UPDATE episodes SET link_id=? WHERE series_name=? AND link_id IS NULL",
            (link_id, series_name)
        )

    conn.commit()
    conn.close()


create_db()
upgrade_database()
link_old_series()


# =========================================================
# 🛠️ معالجة وتنظيف النصوص
# =========================================================

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def extract_quality(text: str) -> str | None:
    if not text:
        return None

    text = str(text).lower()

    patterns = [
        ("2160p", r'\b(?:2160p?|4k)\b'),
        ("1080p", r'\b1080p?\b'),
        ("720p",  r'\b720p?\b'),
        ("480p",  r'\b480p?\b'),
        ("360p",  r'\b360p?\b'),
        ("240p",  r'\b240p?\b'),
        ("144p",  r'\b144p?\b'),
    ]

    for quality, pattern in patterns:
        if re.search(pattern, text, re.I):
            return quality

    return None


def normalize_quality(value):
    """توحيد أسماء الجودة؛ الجودة العادية أو غير المحددة تعامل كـ HD."""
    text = str(value or "").strip().lower().replace(" ", "")
    if not text:
        return "HD"
    if text in {"4k", "2160", "2160p", "uhd"}:
        return "2160p"
    if text in {"fhd", "fullhd", "1080", "1080p"}:
        return "1080p"
    if text in {"hd", "720", "720p"}:
        return "720p"
    if text in {"480", "480p"}:
        return "480p"
    if text in {"360", "360p"}:
        return "360p"
    if text in {"240", "240p"}:
        return "240p"
    if text in {"144", "144p"}:
        return "144p"
    detected = extract_quality(text)
    return detected or "HD"


def clean_name(text):
    if not text:
        return ""
    text = re.sub(r'@\S+', '', text)
    text = re.sub(r'#\S+', '', text)
    text = re.sub(r'[^a-zA-Z0-9\u0600-\u06FF ]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _normalize_parse_text(text: str) -> str:
    """تجهيز النص للتحليل"""
    if not text:
        return ""
    text = str(text).strip()
    text = text.translate(ARABIC_DIGITS)
    text = re.sub(r'\s+', ' ', text)
    return text


def parse_season_episode(text: str) -> dict:
    text = _normalize_parse_text(text)
    if not text:
        return {"season": None, "episode": None}

    match = re.search(r'\bs\s*(\d{1,2})\s*[-_. ]?\s*e\s*(\d{1,3})\b', text, re.I)
    if match:
        return {"season": int(match.group(1)), "episode": int(match.group(2))}

    match = re.search(r'\b(\d{1,2})\s*x\s*(\d{1,3})\b', text, re.I)
    if match:
        return {"season": int(match.group(1)), "episode": int(match.group(2))}

    match = re.search(r'\bseason\s*(\d{1,2})\s*(?:episode|ep)\s*(\d{1,3})\b', text, re.I)
    if match:
        return {"season": int(match.group(1)), "episode": int(match.group(2))}

    match = re.search(r'(?:الموسم|موسم)\s*(\d{1,2})\s*(?:الحلقة|الحلقه|حلقة)\s*(\d{1,3})\b', text, re.I)
    if match:
        return {"season": int(match.group(1)), "episode": int(match.group(2))}

    match = re.search(r'(?:الحلقة|الحلقه|حلقة|episode|ep)\s*(\d{1,3})\b', text, re.I)
    if match:
        return {"season": None, "episode": int(match.group(1))}

    match = re.search(r'(?:الموسم|موسم)\s*(\d{1,2})\b', text, re.I)
    if match:
        return {"season": int(match.group(1)), "episode": None}

    match = re.search(r'\bseason\s*(\d{1,2})\b', text, re.I)
    if match:
        return {"season": int(match.group(1)), "episode": None}

    match = re.search(r'\bs\s*(\d{1,2})\b', text, re.I)
    if match:
        return {"season": int(match.group(1)), "episode": None}

    match = re.search(r'(?:جزء|الجزء|part)\s*(\d{1,2})\b', text, re.I)
    if match:
        return {"season": int(match.group(1)), "episode": None}

    return {"season": None, "episode": None}


def extract_season(text: str):
    return parse_season_episode(text)["season"]


def extract_part(text: str):
    return parse_season_episode(text)["season"]


def extract_episode(text: str):
    return parse_season_episode(text)["episode"]


def extract_episode_safe(text: str):
    return parse_season_episode(text)["episode"]


def normalize_series_name(name: str) -> str:
    if not name:
        return ""

    name = str(name).lower().strip()
    name = re.sub(r'@\S+', '', name)
    name = re.sub(r'#\S+', '', name)

    arabic_nums = "٠١٢٣٤٥٦٧٨٩"
    english_nums = "0123456789"
    trans = str.maketrans(arabic_nums, english_nums)
    name = name.translate(trans)

    junk_words = [
        "مسلسل", "فيلم", "الحلقة", "حلقة",
        "ep", "episode", "season", "part"
    ]
    for w in junk_words:
        name = re.sub(rf"\b{w}\b", "", name, flags=re.IGNORECASE)

    name = re.sub(r"[^a-z0-9\u0600-\u06FF ]+", " ", name)
    name = " ".join(name.split())
    return name


def normalize(text):
    text = text.lower()
    replacements = {
        "أ": "ا", "إ": "ا", "آ": "ا",
        "ة": "ه", "ى": "ي",
        "ؤ": "و", "ئ": "ي"
    }
    for k, v in replacements.items():
        text = text.replace(k, v)

    text = re.sub(r'[^\w\s\u0600-\u06ff]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def word_match(query, text):
    q_words = normalize(query).split()
    t_words = normalize(text).split()

    if not q_words or not t_words:
        return False

    matches = sum(1 for w in q_words if w in t_words)
    return matches / len(q_words) >= 0.6


def normalize_numbers(text: str) -> str:
    arabic_nums = "٠١٢٣٤٥٦٧٨٩"
    english_nums = "0123456789"
    for a, e in zip(arabic_nums, english_nums):
        text = text.replace(a, e)
    return text


def clean_series_title(name: str) -> str:
    if not name:
        return ""
    text = name.lower()
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'(4k|2160p?|1080p?|720p?|480p?|360p?|144p?|fhd|hd|sd)', '', text)
    text = re.sub(r'(bluray|webrip|web-dl|hdrip|dvdrip|x264|x265)', '', text)
    text = re.sub(r'[._\-]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def get_base_series_name(name: str) -> str:
    if not name:
        return ""
    text = _normalize_parse_text(name)
    text = re.sub(r'\b(?:4k|2160p?|1080p?|720p?|480p?|360p?|240p?|144p?|fhd|hd|sd)\b', '', text, flags=re.I)
    text = re.sub(r'\bs\s*\d{1,2}\s*[-_. ]?\s*e\s*\d{1,3}\b', '', text, flags=re.I)
    text = re.sub(r'\b\d{1,2}\s*x\s*\d{1,3}\b', '', text, flags=re.I)
    text = re.sub(r'\bseason\s*\d{1,2}\s*(?:episode|ep)\s*\d{1,3}\b', '', text, flags=re.I)
    text = re.sub(r'(?:الموسم|موسم)\s*\d{1,2}\s*(?:الحلقة|الحلقه|حلقة)\s*\d{1,3}', '', text, flags=re.I)
    text = re.sub(r'(?:الموسم|موسم)\s*\d{1,2}', '', text, flags=re.I)
    text = re.sub(r'\bseason\s*\d{1,2}\b', '', text, flags=re.I)
    text = re.sub(r'\bs\s*\d{1,2}\b', '', text, flags=re.I)
    text = re.sub(r'(?:الجزء|جزء|part)\s*\d{1,2}\b', '', text, flags=re.I)
    text = re.sub(r'(?:الحلقة|الحلقه|حلقة|episode|ep)\s*\d{1,3}\b', '', text, flags=re.I)
    text = re.sub(r'[_\-.]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip(' -_.')
    return normalize_series_name(text)


def extract_year(text):
    if not text:
        return None
    match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    return match.group(1) if match else None


def safe_markdown(text: str):
    if not text:
        return ""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    for ch in escape_chars:
        text = text.replace(ch, f"\{ch}")
    return text


def format_button_text(
    title: str,
    episode: int | None = None,
    quality: str | None = None,
    max_title_length: int = 18
) -> str:
    clean_title = title.strip()
    if len(clean_title) > max_title_length:
        clean_title = clean_title[:max_title_length - 1] + "…"

    parts = []
    if episode is not None:
        parts.append(f"ح{episode}")
    if quality:
        parts.append(quality.upper().replace(" ", ""))

    extra = " | ".join(parts)
    if extra:
        return f"📺 {clean_title} | {extra}"
    return f"🎬 {clean_title}"


def smart_parse_query(text: str):
    if not text:
        return "", None

    text = normalize_numbers(text)
    text = re.sub(r'[^\w\s\u0600-\u06FF]', ' ', text)
    episode = extract_episode_safe(text)
    text = re.sub(r'(حلقة|الحلقه|ep|episode)\s*\d*', ' ', text, flags=re.I)
    text = re.sub(r'\b(360|480|720|1080)\b', ' ', text)
    text = re.sub(r'(الجودة|quality|حجم|size|ميجا|mb|gb)', ' ', text, flags=re.I)

    clean = normalize_series_name(text.strip())
    return clean or "", episode


def get_series_name_for_caption(series_name: str):
    clean = normalize_series_name(series_name)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT series_name FROM series_captions")
    rows = cursor.fetchall()
    conn.close()

    for (db_name,) in rows:
        if normalize_series_name(db_name) == clean:
            return db_name
    return None


def parse_caption(raw_caption):
    if not raw_caption:
        raw_caption = ""

    text = str(raw_caption).strip()
    clean_for_numbers = re.sub(r'(4k|2160p?|1080p?|720p?|480p?|360p?)', '', text, flags=re.I)

    quality = extract_quality(text)
    season = extract_season(clean_for_numbers)
    episode = extract_episode(clean_for_numbers)
    part = extract_part(clean_for_numbers)

    first_line = text.split("\n")[0].strip()
    clean = clean_series_title(first_line)
    base_name = get_base_series_name(clean) or "Unknown"

    final_season = season if season else part

    if final_season:
        series_name = f"{base_name} الموسم {final_season}"
    else:
        series_name = base_name

    title_parts = [base_name]
    if final_season is not None:
        title_parts.append(f"الموسم {final_season}")
    if episode is not None:
        title_parts.append(f"الحلقة {episode}")
    if quality:
        title_parts.append(str(quality))

    final_title = " - ".join(title_parts)
    content_type = "series" if episode is not None else "movie"

    return {
        "type": content_type,
        "series_name": series_name,
        "season": final_season,
        "episode": episode,
        "quality": quality,
        "final_title": final_title
    }


# =========================================================
# 🌐 TMDB وجلب القصة بدقة تامة (مع دعم الذكاء الاصطناعي)
# =========================================================

BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

def clean_query(title: str):
    title = re.sub(r'\(.*?\)', '', title)
    title = re.sub(r'\[.*?\]', '', title)
    title = re.sub(r'(حلقة|episode|ep|season|موسم|جزء|part)\s*\d+', '', title, flags=re.I)
    title = re.sub(r'(720p|1080p|480p|360p|4k|hd)', '', title, flags=re.I)
    title = re.sub(r'\s+', ' ', title)
    return title.strip()


def get_ai_fallback_story(title: str, media_type: str = "series") -> str:
    """توليد قصة دقيقة وممتعة بالذكاء الاصطناعي لو لم تتوفر في TMDB لتفادي جملة لا توجد قصة."""
    try:
        category = "مسلسل" if media_type in ["series", "tv"] else "فيلم"
        prompt = (
            f"أنت خبير سينمائي. اكتب نبذة وقصة دقيقة ومشوقة لـ {category} ({title}) "
            "في حدود 3 إلى 5 أسطر بأسلوب جذاب باللغة العربية دون أي مقدمات أو هوامش."
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        if response and response.text:
            story = response.text.strip()
            if len(story) > 15:
                return story
    except Exception as e:
        print("AI STORY GENERATION ERROR:", e)
    return "تدور أحداث هذا العمل الممتع في إطار مشوق من الدراما والأحداث المثيرة التي تستحق المشاهدة."


def search_tmdb(title, is_series=True):
    query = clean_query(title)
    if not query:
        return None

    try:
        endpoint = "/search/tv" if is_series else "/search/movie"
        search_url = BASE_URL + endpoint
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "ar"
        }
        r = requests.get(search_url, params=params, timeout=10)
        data = r.json()
        if not data.get("results"):
            return None

        result = data["results"][0]
        tmdb_id = result["id"]

        details_endpoint = f"/tv/{tmdb_id}" if is_series else f"/movie/{tmdb_id}"
        details_r = requests.get(BASE_URL + details_endpoint, params={"api_key": TMDB_API_KEY, "language": "ar"}, timeout=10)
        details = details_r.json()

        # لو القصة بالعربي غير موجودة، نجرب الإنجليزي أو الذكاء الاصطناعي فوراً
        overview = str(details.get("overview") or "").strip()
        if not overview or overview == "لا توجد قصة." or len(overview) < 10:
            try:
                en_r = requests.get(BASE_URL + details_endpoint, params={"api_key": TMDB_API_KEY, "language": "en-US"}, timeout=6)
                en_overview = en_r.json().get("overview", "")
                if en_overview and len(en_overview) > 15:
                    overview = get_ai_fallback_story(f"{title} (Summary: {en_overview[:200]})", "series" if is_series else "movie")
                else:
                    overview = get_ai_fallback_story(title, "series" if is_series else "movie")
            except Exception:
                overview = get_ai_fallback_story(title, "series" if is_series else "movie")

        credits_endpoint = f"/tv/{tmdb_id}/credits" if is_series else f"/movie/{tmdb_id}/credits"
        credits_r = requests.get(BASE_URL + credits_endpoint, params={"api_key": TMDB_API_KEY, "language": "ar"}, timeout=10)
        credits = credits_r.json()

        poster = (IMAGE_BASE + details["poster_path"]) if details.get("poster_path") else None
        genres = ", ".join([g["name"] for g in details.get("genres", [])]) or "غير معروف"

        if is_series:
            country = ", ".join(details.get("origin_country", [])) or "غير معروف"
        else:
            country = ", ".join([c["name"] for c in details.get("production_countries", [])]) or "غير معروف"

        director = "غير معروف"
        for crew in credits.get("crew", []):
            if crew.get("job") == "Director":
                director = crew.get("name")
                break

        actors_list = [actor.get("name") for actor in credits.get("cast", [])[:5]]
        actors = ", ".join(actors_list) if actors_list else "غير معروف"

        return {
            "tmdb_id": tmdb_id,
            "name": details.get("name") or details.get("title") or query,
            "overview": overview or get_ai_fallback_story(title, "series" if is_series else "movie"),
            "rating": details.get("vote_average", "N/A"),
            "date": details.get("first_air_date") or details.get("release_date") or "غير معروف",
            "poster": poster,
            "genres": genres,
            "country": country,
            "director": director,
            "actors": actors,
            "seasons": details.get("number_of_seasons", 0) if is_series else None
        }
    except Exception as e:
        print("TMDB ERROR:", e)
        return None


def extract_caption_details(caption, fallback_name=""):
    caption = str(caption or "")
    def field(pattern, default="غير متوفر"):
        m = re.search(pattern, caption, re.I | re.M)
        return m.group(1).strip() if m else default

    name = field(r"🎬\s*(.+)", fallback_name or "غير متوفر")
    actors = field(r"(?:👥\s*(?:البطولة|الممثلين)\s*:?\s*\n)(.*?)(?=\n(?:⏱️|🗣️|📺|📝|🌍|🎭|🎬)|\Z)", "غير متوفر")
    country = field(r"🌍\s*(?:البلد|بلد الإنتاج)\s*:\s*(.+)")
    seasons = field(r"📺\s*(?:عدد المواسم|المواسم)\s*:\s*(.+)", "")
    story = field(r"(?:📝\s*القصة\s*:?\s*\n)(.*?)(?=\n(?:⭐|📅|🌍|🎭|🎬|👥|⏱️|🗣️|📺)|\Z)", "")
    story = re.sub(r"__PLOT_(?:START|END)__", "", story).strip()
    if not story or "لا توجد قصة" in story:
        story = get_ai_fallback_story(fallback_name or name)
    return {"name": name, "actors": actors, "country": country, "seasons": seasons, "story": story}


def build_work_caption(caption, fallback_name="", media_type="series", episode_num=None):
    """كابشن البوست (موحد للرسمي والدعائي) شامل القصة المشوقة والممثلين والبيانات."""
    details = extract_caption_details(caption, fallback_name)
    display_title = details['name'] if details['name'] != "غير متوفر" else (fallback_name or "عمل مميز")

    lines = [f"🔥 <b>{html.escape(display_title)}</b>"]
    if details["actors"] and details["actors"] != "غير متوفر":
        lines.append(f"🎭 <b>الممثلين:</b> {html.escape(details['actors'])}")
    if details["country"] and details["country"] != "غير متوفر":
        lines.append(f"🌍 <b>بلد الإنتاج:</b> {html.escape(details['country'])}")
    if media_type in ("series", "tv") and details["seasons"]:
        lines.append(f"📺 <b>المواسم:</b> {html.escape(str(details['seasons']))}")
    if episode_num is not None:
        lines.append(f"🎞️ <b>الحلقة:</b> {html.escape(str(episode_num))}")

    story = details.get("story") or get_ai_fallback_story(display_title, media_type)
    story_clean = html.escape(story)
    lines.append(f"\n📖 <b>القصة:</b>\n<blockquote expandable>{story_clean}</blockquote>")
    return "\n".join(lines)


def get_series_caption_exact(cursor, title):
    clean_title = get_base_series_name(title)
    cursor.execute(
        "SELECT photo_file_id, caption FROM series_captions WHERE series_name = ?",
        (clean_title,)
    )
    return cursor.fetchone()


def get_series_caption_fuzzy(cursor, detected_name):
    key = normalize_series_name(detected_name)
    cursor.execute("SELECT series_name, photo_file_id, caption FROM series_captions")
    rows = cursor.fetchall()

    for s_name, photo_id, caption in rows:
        db_key = normalize_series_name(s_name)
        if db_key in key or key in db_key:
            return photo_id, caption
    return None, None


def save_series_caption(cursor, title, poster, caption, series_id=None):
    clean_title = get_base_series_name(title)
    sid = series_id or get_or_create_series_id(clean_title)
    cursor.execute(
        """
        INSERT OR REPLACE INTO series_captions
        (series_id, series_name, photo_file_id, caption)
        VALUES (?, ?, ?, ?)
        """,
        (sid, clean_title, poster, caption)
    )


def get_caption_with_fallback(cursor, title, media_type="series"):
    clean_title = get_base_series_name(title)

    # 1. Exact DB
    row = get_series_caption_exact(cursor, clean_title)
    if row and row[0]:
        return row[0], row[1]

    # 2. TMDB
    is_series = media_type in ["series", "tv"]
    data = search_tmdb(clean_title, is_series)

    if data and data.get("poster"):
        poster = data.get("poster")
        name = data.get("name", clean_title)
        actors = data.get("actors", "غير متوفر")
        overview = data.get("overview") or get_ai_fallback_story(clean_title, media_type)
        country = data.get("country", "غير متوفر")
        seasons = data.get("seasons") or 0
        caption = f"🎬 {name}\n🌍 البلد : {country}\n👥 البطولة :\n{actors}\n"
        if is_series and seasons:
            caption += f"📺 عدد المواسم : {seasons}\n"
        caption += f"📝 القصة :\n\n{overview}\n"

        save_series_caption(cursor, clean_title, poster, caption)
        return poster, caption

    # 3. Fuzzy DB
    row = get_series_caption_fuzzy(cursor, clean_title)
    if row and row[0]:
        return row[0], row[1]

    # 4. لو مفيش خالص ننشئ كابشن بقصة بالذكاء الاصطناعي
    generated_story = get_ai_fallback_story(clean_title, media_type)
    fallback_caption = f"🎬 {clean_title}\n📝 القصة :\n\n{generated_story}\n"
    return None, fallback_caption


# =========================================================
# 🛡️ نظام الحماية وفحص التحويلات
# =========================================================

def check_transfer(user):
    user_id = user.id
    now = time.time()

    if user_id in BLOCKED_USERS:
        return False

    data = USER_TRANSFERS.get(user_id)
    if not data:
        USER_TRANSFERS[user_id] = {"count": 1, "start": now}
        return True

    if now - data["start"] > TIME_WINDOW:
        data["count"] = 1
        data["start"] = now
        return True

    data["count"] += 1
    if data["count"] >= MAX_TRANSFERS:
        alert_admin(user, data["count"])
        if AUTO_BLOCK:
            BLOCKED_USERS.add(user_id)
        return False

    return True


def alert_admin(user, count):
    text = (
        "🚨 *إنذار تحويلات*\n\n"
        f"👤 الاسم: {user.first_name}\n"
        f"🆔 ID: `{user.id}`\n"
        f"📛 Username: @{user.username}\n"
        f"📊 التحويلات: {count}\n"
        f"⛔ الحالة: {'تم الحظر' if AUTO_BLOCK else 'إنذار فقط'}"
    )
    bot.send_message(ADMIN_ID, text, parse_mode="Markdown")


# =========================================================
# 💳 الاشتراكات وتنبيهات الانتهاء
# =========================================================

def check_subscriptions_expiry():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, end_date FROM subscriptions")
    users = cursor.fetchall()

    now_dt = datetime.now()
    now_ts = time.time()

    for user_id, end_date in users:
        try:
            expiry_date = datetime.fromisoformat(end_date)
            delta = expiry_date - now_dt
            days_left = delta.days
            key = f"{user_id}_{days_left}"

            if key in SUBS_NOTIFIED and (now_ts - SUBS_NOTIFIED[key] < 43200):
                continue

            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton(
                    "✨ تواصل للتجديد",
                    url=f"https://t.me/{OWNER_USERNAME}"
                )
            )

            if days_left == 3:
                bot.send_message(user_id, "⏳ فاضل 3 أيام على انتهاء الاشتراك 🔥", reply_markup=markup)
                SUBS_NOTIFIED[key] = now_ts
            elif days_left == 1:
                bot.send_message(user_id, "🚨 فاضل يوم واحد فقط على انتهاء الاشتراك", reply_markup=markup)
                SUBS_NOTIFIED[key] = now_ts
            elif days_left <= 0:
                bot.send_message(user_id, "جدد اشتراكك علشان تقدر تشوف المسلسلات والأفلام براحتك ❤️", reply_markup=markup)
                SUBS_NOTIFIED[key] = now_ts
        except Exception as e:
            print("Expiry Error:", e)

    conn.close()


def expiry_loop():
    while True:
        check_subscriptions_expiry()
        time.sleep(86400)


def get_subscription_info(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT start_date, end_date FROM subscriptions WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    start_date, end_date = row
    end_date_dt = datetime.fromisoformat(end_date)
    now = datetime.now()
    delta = end_date_dt - now

    if delta.total_seconds() < 0:
        days = 0
        hours = 0
    else:
        days = delta.days
        hours = delta.seconds // 3600

    return {
        "start": start_date,
        "end": end_date,
        "days_left": days,
        "hours_left": hours
    }


def update_subscription(user_id, days=0, hours=0, mode="add"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT end_date FROM subscriptions WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    now = datetime.now()

    if row:
        end_date = datetime.fromisoformat(row[0])
        if end_date < now:
            end_date = now
    else:
        end_date = now
        cursor.execute(
            """
            INSERT OR IGNORE INTO subscriptions (user_id, start_date, end_date)
            VALUES (?, ?, ?)
            """,
            (user_id, now.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S"))
        )

    delta = timedelta(days=days, hours=hours)
    if mode == "add":
        new_end = end_date + delta
    else:
        new_end = end_date - delta
        if new_end < now:
            new_end = now

    cursor.execute(
        "UPDATE subscriptions SET end_date = ? WHERE user_id = ?",
        (new_end.strftime("%Y-%m-%d %H:%M:%S"), user_id)
    )
    conn.commit()
    conn.close()
    return new_end


# =========================================================
# 🎬 ترشيحات الأفلام العشوائية والقناة
# =========================================================

def get_random_movie():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        def is_strict_movie(series_name, episode_name):
            text = f"{series_name or ''} {episode_name or ''}".strip()
            if not text:
                return False

            normalized = text.lower()
            normalized = re.sub(r'[_\-./]+', ' ', normalized)
            normalized = re.sub(r'\s+', ' ', normalized).strip()

            forbidden_arabic = [
                "مسلسل", "المسلسل", "حلقة", "الحلقة", "حلقه", "الحلقه",
                "موسم", "الموسم", "جزء", "الجزء", "الحلقات", "حلقات", "مسلسلات"
            ]
            for word in forbidden_arabic:
                if word in normalized:
                    return False

            forbidden_english = [
                "series", "season", "episode", "episodes", "ep",
                "s01", "s02", "s03", "s04", "s05"
            ]
            for word in forbidden_english:
                if re.search(rf'(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])', normalized, re.IGNORECASE):
                    return False

            if re.search(r'(?<![a-z0-9])s\d+\s*e\d+(?![a-z0-9])', normalized, re.I): return False
            if re.search(r'(?<![a-z0-9])se\d+(?![a-z0-9])', normalized, re.I): return False
            if re.search(r'(?<![a-z0-9])e\d+(?![a-z0-9])', normalized, re.I): return False
            if re.search(r'(?<![a-z0-9])ep\d+(?![a-z0-9])', normalized, re.I): return False
            if re.search(r'(?<![a-z0-9])s\d+(?![a-z0-9])', normalized, re.I): return False
            if re.search(r'(?<![a-z0-9])season\s*\d*', normalized, re.I): return False
            if re.search(r'(?<![a-z0-9])episode\s*\d*', normalized, re.I): return False
            if re.search(r'(?<![a-z0-9])part\s*\d+', normalized, re.I): return False

            episode_patterns = [
                r'(?<![a-z0-9])\d+x\d+(?![a-z0-9])',
                r'(?<![a-z0-9])\d{1,3}\s*x\s*\d{1,3}(?![a-z0-9])',
                r'(?<![a-z0-9])\d{1,3}\s*[-.]\s*\d{1,3}(?![a-z0-9])'
            ]
            for pattern in episode_patterns:
                if re.search(pattern, normalized, re.I):
                    return False

            return True

        cursor.execute("SELECT id, series_name, episode_name, quality FROM episodes")
        rows = cursor.fetchall()
        if not rows:
            return None

        movies = {}
        for ep_id, series_name, episode_name, quality in rows:
            s_clean = str(series_name or "").strip()
            e_clean = str(episode_name or "").strip()
            if not s_clean:
                continue
            if not is_strict_movie(s_clean, e_clean):
                continue
            if s_clean not in movies:
                movies[s_clean] = (ep_id, s_clean, quality or "HD")

        movies_list = list(movies.values())
        if not movies_list:
            return None

        cursor.execute("SELECT movie_name FROM movie_recommendations")
        posted = {str(row[0]).strip() for row in cursor.fetchall() if row[0]}
        available = [m for m in movies_list if m[1] not in posted]

        if not available:
            cursor.execute("DELETE FROM movie_recommendations")
            conn.commit()
            available = movies_list

        if not available:
            return None

        return random.choice(available)
    except Exception as e:
        print("❌ GET RANDOM MOVIE ERROR:", repr(e))
        return None
    finally:
        conn.close()


def publish_movie_recommendation():
    movie = get_random_movie()
    if not movie:
        return False

    ep_id, movie_name, quality = movie
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        caption_data = get_caption_with_fallback(cursor, movie_name, media_type="movie")
        photo_id, caption_text = caption_data if caption_data else (None, None)

        if not caption_text:
            caption_text = f"🎬 *{safe_markdown(movie_name)}*"

        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton(
                "🎬 شوف الفيلم",
                url=f"https://t.me/{BOT_USERNAME}?start=rec_{ep_id}"
            )
        )

        sent_successfully = False
        if photo_id:
            try:
                bot.send_photo(
                    RECOMMEND_CHANNEL_ID,
                    photo_id,
                    caption=safe_markdown(caption_text),
                    parse_mode="Markdown",
                    reply_markup=markup
                )
                sent_successfully = True
            except Exception:
                try:
                    bot.send_message(
                        RECOMMEND_CHANNEL_ID,
                        safe_markdown(caption_text),
                        parse_mode="Markdown",
                        reply_markup=markup
                    )
                    sent_successfully = True
                except Exception as e:
                    print("❌ SEND RECOMMENDATION TEXT FALLBACK ERROR:", e)
        else:
            try:
                bot.send_message(
                    RECOMMEND_CHANNEL_ID,
                    safe_markdown(caption_text),
                    parse_mode="Markdown",
                    reply_markup=markup
                )
                sent_successfully = True
            except Exception as e:
                print("❌ SEND RECOMMENDATION ERROR:", e)

        if not sent_successfully:
            return False

        cursor.execute(
            "INSERT OR IGNORE INTO movie_recommendations (movie_name, posted_at) VALUES (?, ?)",
            (movie_name, datetime.now().isoformat())
        )
        conn.commit()
        return True
    except Exception as e:
        print("❌ PUBLISH RECOMMENDATION ERROR:", repr(e))
        return False
    finally:
        conn.close()


def handle_recommendation_start(message, ep_id):
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT file_id, episode_name FROM episodes WHERE id = ?", (ep_id,))
        episode = cursor.fetchone()
        if not episode:
            bot.send_message(message.chat.id, "❌ الفيلم غير موجود أو تم حذفه.")
            return
        file_id, episode_name = episode
    finally:
        conn.close()

    is_blocked = user_id in BLOCKED_USERS
    try:
        bot.send_video(
            message.chat.id,
            file_id,
            caption=episode_name,
            parse_mode="Markdown",
            protect_content=is_blocked
        )
    except Exception as e:
        print(f"❌ RECOMMENDATION SEND ERROR: {repr(e)}")
        bot.send_message(message.chat.id, "❌ حصل خطأ أثناء إرسال الفيلم، حاول مرة أخرى.")


def recommendation_loop():
    print("🎬 RECOMMENDATION SYSTEM STARTED", flush=True)
    try:
        publish_movie_recommendation()
    except Exception as e:
        print("❌ FIRST RECOMMENDATION ERROR:", repr(e))

    while True:
        try:
            time.sleep(RECOMMEND_INTERVAL)
            publish_movie_recommendation()
        except Exception as e:
            print("❌ RECOMMENDATION LOOP ERROR:", repr(e))
            time.sleep(30)


# =========================================================
# 🔔 إشعارات الحلقات الجديدة (البوست الرسمي والدعائي متطابقان)
# =========================================================

def send_new_episode_notification(series_name, episode_num, quality, ep_id):
    if not NOTIFICATIONS_ENABLED:
        return

    is_movie = episode_num is None
    quality_text = str(quality or "HD").strip().lower()

    if not is_movie and quality_text not in ["720", "720p", "hd"]:
        return

    notification_key = f"{series_name}_{'movie' if is_movie else episode_num}_{quality_text}"
    now = time.time()
    if notification_key in LAST_NOTIFIED and now - LAST_NOTIFIED[notification_key] < 60:
        return
    LAST_NOTIFIED[notification_key] = now

    conn = sqlite3.connect(DB_NAME)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT series_id, media_type FROM episodes WHERE id = ?", (ep_id,))
        row = cursor.fetchone()
        series_id = row[0] if row and row[0] else get_or_create_series_id(series_name, "movie" if is_movie else "series")
        media_type = row[1] if row and row[1] else ("movie" if is_movie else "series")

        caption_data = get_caption_with_fallback(
            cursor, series_name, media_type=media_type
        )
        photo_id, raw_caption = caption_data if caption_data else (None, "")
    finally:
        conn.close()

    details = extract_caption_details(raw_caption, series_name)
    display_name = details["name"] if details["name"] != "غير متوفر" else series_name

    # بناء الكابشن المشترك والمتطابق للبوست الرسمي والدعائي
    post_caption = build_work_caption(raw_caption, display_name, media_type=media_type, episode_num=episode_num)

    # 1. البوست الرسمي: الزرار يتحول لشات البوت وينادي دالة البحث عن العمل
    if is_movie:
        official_btn_text = "🎬 مشاهدة الفيلم"
        official_deep_link = f"https://t.me/{BOT_USERNAME}?start=show_mov_{ep_id}"
    else:
        official_btn_text = "📺 مشاهدة المسلسل"
        official_deep_link = f"https://t.me/{BOT_USERNAME}?start=show_ser_{series_id}"

    official_markup = types.InlineKeyboardMarkup()
    official_markup.add(types.InlineKeyboardButton(official_btn_text, url=official_deep_link))

    try:
        # إرسال البوست الرسمي للجروب
        if photo_id:
            main_msg = bot.send_photo(
                GROUP_ID, photo_id, caption=post_caption,
                reply_markup=official_markup, parse_mode="HTML"
            )
        else:
            main_msg = bot.send_message(
                GROUP_ID, post_caption, reply_markup=official_markup, parse_mode="HTML"
            )

        try:
            bot.pin_chat_message(GROUP_ID, main_msg.message_id, disable_notification=True)
        except Exception:
            pass

        # إشعار المشتركين بالمفضلة
        if not is_movie:
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM favorites WHERE series_name LIKE ? OR series_id = ?", (f"%{series_name}%", series_id))
                fans = cursor.fetchall()
                conn.close()
            except Exception:
                fans = []

            for (fan_id,) in fans:
                try:
                    fan_caption = (
                        f"🔔 <b>مسلسل من مفضلتك نزلت له حلقة جديدة!</b>\n\n"
                        f"🎬 {html.escape(display_name)}\n"
                        f"🎞️ الحلقة: {html.escape(str(episode_num))}\n"
                        f"📺 الجودة: {quality_text.upper()}"
                    )
                    fan_markup = types.InlineKeyboardMarkup()
                    fan_markup.add(types.InlineKeyboardButton(
                        "▶️ شاهد الآن", url=f"https://t.me/{BOT_USERNAME}?start=episode_{ep_id}"
                    ))
                    if photo_id:
                        bot.send_photo(fan_id, photo_id, caption=fan_caption, reply_markup=fan_markup, parse_mode="HTML")
                    else:
                        bot.send_message(fan_id, fan_caption, reply_markup=fan_markup, parse_mode="HTML")
                except Exception:
                    pass

        # 2. البوست الدعائي: نفس البوست بالضبط ولكن الزر يحول لشات صاحب البوت مع كلمة اشتراك
        owner_username = str(OWNER_USERNAME).lstrip("@")
        promo_url = f"https://t.me/{owner_username}?text={urllib.parse.quote('اشتراك')}"
        promo_markup = types.InlineKeyboardMarkup()
        promo_markup.add(types.InlineKeyboardButton("🔥 اشتراك", url=promo_url))

        if photo_id:
            bot.send_photo(PROMO_GROUP_ID, photo_id, caption=post_caption, reply_markup=promo_markup, parse_mode="HTML")
        else:
            bot.send_message(PROMO_GROUP_ID, post_caption, reply_markup=promo_markup, parse_mode="HTML")

    except Exception as e:
        print("SEND NOTIFICATION ERROR:", repr(e))


# =========================================================
# 📦 نظام استلام الحلقات والدفعات وحفظ كل أعمدة episodes
# =========================================================

def extract_batch_number(text):
    if not text:
        return None
    text = text.strip().translate(ARABIC_DIGITS)
    if re.fullmatch(r"\d{1,4}", text):
        return int(text)
    return None


def extract_season_episode_batch(text):
    if not text:
        return None
    text = text.strip().upper()
    match = re.fullmatch(r"S\s*(\d{1,2})\s*E\s*(\d{1,3})", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def finish_batch():
    global WAITING_FOR_BATCH_NAME
    with BATCH_LOCK:
        if not BATCH_VIDEOS or WAITING_FOR_BATCH_NAME:
            return
        WAITING_FOR_BATCH_NAME = True
        count = len(BATCH_VIDEOS)

    bot.send_message(
        ADMIN_ID,
        f"🎬 تم اكتشاف دفعة من {count} فيديو\n\n"
        f"✏️ اكتب اسم المسلسل الذي تريد تسجيل الفيديوهات به:"
    )


def restart_batch_timer():
    global BATCH_TIMER
    if BATCH_TIMER:
        try:
            BATCH_TIMER.cancel()
        except Exception:
            pass

    BATCH_TIMER = threading.Timer(BATCH_WAIT_SECONDS, finish_batch)
    BATCH_TIMER.daemon = True
    BATCH_TIMER.start()


@bot.channel_post_handler(content_types=['video', 'document', 'photo'])
def save_episode_from_channel(message):
    if not message.sender_chat or message.sender_chat.id != CONTENT_CHANNEL_ID or not message.caption:
        return

    raw_caption = message.caption.strip()
    batch_number = extract_batch_number(raw_caption)
    season_episode = extract_season_episode_batch(raw_caption)

    # حالة الدفعات المجمعة
    if batch_number is not None or season_episode:
        file_id = None
        if message.video:
            file_id = message.video.file_id
        elif message.document:
            file_id = message.document.file_id

        if not file_id:
            return

        data = parse_caption(raw_caption)
        quality = normalize_quality(data.get("quality") or extract_quality(raw_caption) or "HD")

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM episodes WHERE file_id=?", (file_id,))
        already_saved = cursor.fetchone()
        conn.close()

        if already_saved:
            return

        with BATCH_LOCK:
            BATCH_VIDEOS.append({
                "file_id": file_id,
                "quality": quality,
                "number": batch_number,
                "season_episode": season_episode,
                "caption": raw_caption
            })
            batch_count = len(BATCH_VIDEOS)

        print(f"🔥 BATCH VIDEO ADDED: {raw_caption} | TOTAL: {batch_count}")
        restart_batch_timer()
        return

    # استخراج البيانات العادية وحفظ كل الأعمدة
    data = parse_caption(raw_caption)
    series_name_raw = data.get("series_name", "")
    clean_title = clean_series_title(series_name_raw)
    base_series_name = get_base_series_name(clean_title)
    part_number = extract_part(clean_title)
    season_num = extract_season(raw_caption) or part_number or 1
    episode_num = extract_episode_safe(raw_caption)
    release_year = extract_year(raw_caption)
    quality = normalize_quality(data.get("quality") or extract_quality(raw_caption) or "HD")
    media_type = "series" if episode_num is not None else "movie"

    if part_number:
        series_name = f"{base_series_name} الموسم {part_number}"
    else:
        series_name = base_series_name

    if not series_name:
        bot.send_message(ADMIN_ID, "❌ لم أستطع تحديد اسم المسلسل")
        return

    series_id = get_or_create_series_id(base_series_name, media_type)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # لو بوستر/صورة
    if message.photo:
        photo_file_id = message.photo[-1].file_id
        cursor.execute("SELECT id FROM series_captions WHERE series_name=?", (series_name,))
        if not cursor.fetchone():
            cursor.execute(
                """
                INSERT INTO series_captions (series_id, series_name, caption, photo_file_id)
                VALUES (?, ?, ?, ?)
                """,
                (series_id, series_name, raw_caption, photo_file_id)
            )
            conn.commit()
        conn.close()
        return

    file_id = None
    if message.video:
        file_id = message.video.file_id
    elif message.document:
        file_id = message.document.file_id

    if not file_id:
        conn.close()
        return

    cursor.execute("SELECT id FROM episodes WHERE file_id=?", (file_id,))
    if cursor.fetchone():
        conn.close()
        return

    if episode_num:
        final_title = f"{series_name} حلقة {episode_num} - {quality}"
    elif release_year:
        final_title = f"{series_name} ({release_year}) - {quality}"
    else:
        final_title = f"{series_name} - {quality}"

    linked_caption = f"[{final_title}](https://t.me/cimabotbest)"

    # جلب رابط مخصص لو وجد في links
    cursor.execute("SELECT link_id FROM links WHERE series_name=? OR series_id=?", (series_name, series_id))
    link_row = cursor.fetchone()
    link_id = link_row[0] if link_row else None

    # حفظ كل الأعمدة بدون استثناء
    cursor.execute(
        """
        INSERT INTO episodes
        (series_id, series_name, episode_name, file_id, quality, media_type, season, episode, release_year, views, added_date, link_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            series_id,
            series_name,
            linked_caption,
            file_id,
            quality,
            media_type,
            season_num if media_type == "series" else 0,
            episode_num if episode_num is not None else 0,
            release_year or "",
            0,
            datetime.now().isoformat(),
            link_id
        )
    )
    conn.commit()
    ep_id = cursor.lastrowid
    conn.close()

    # تنظيف الكاش السريع
    SERIES_CACHE.clear()
    FAST_SEARCH_CACHE.clear()

    # إرسال الإشعار الموحد
    send_new_episode_notification(series_name, episode_num, quality, ep_id)


# =========================================================
# 🚀 محرك بحث صاروخي للأفلام والمسلسلات (Fast Search Engine)
# =========================================================

def fast_search_media(query_raw: str, media_type: str = "series"):
    """محرك بحث سريع جداً يعتمد على التخزين المؤقت والفهارس في أجزاء من الثانية."""
    cache_key = f"{media_type}_{normalize(query_raw)}"
    now = time.time()
    if cache_key in FAST_SEARCH_CACHE:
        val, ts = FAST_SEARCH_CACHE[cache_key]
        if now - ts < FAST_SEARCH_TTL:
            return val

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    q_clean = normalize(query_raw)
    tokens = q_clean.split()
    first_token = tokens[0] if tokens else q_clean

    # جلب أولي سريع باستخدام الفهرس
    cursor.execute(
        """
        SELECT DISTINCT series_name, series_id
        FROM episodes
        WHERE media_type = ? AND series_name LIKE ?
        LIMIT 50
        """,
        (media_type, f"%{first_token}%")
    )
    candidates = cursor.fetchall()

    if not candidates and len(tokens) > 1:
        cursor.execute(
            """
            SELECT DISTINCT series_name, series_id
            FROM episodes
            WHERE media_type = ? AND series_name LIKE ?
            LIMIT 50
            """,
            (media_type, f"%{tokens[1]}%")
        )
        candidates = cursor.fetchall()

    # مطابقة ذكية وسريعة
    matched_names = []
    for s_name, s_id in candidates:
        if word_match(query_raw, s_name):
            matched_names.append((s_name, s_id))

    # لو مفيش، نعمل فحص سريع على كل الأسماء الفريدة
    if not matched_names:
        cursor.execute("SELECT DISTINCT series_name, series_id FROM episodes WHERE media_type = ? LIMIT 200", (media_type,))
        for s_name, s_id in cursor.fetchall():
            if word_match(query_raw, s_name):
                matched_names.append((s_name, s_id))
                break

    conn.close()
    FAST_SEARCH_CACHE[cache_key] = (matched_names, now)
    return matched_names


# =========================================================
# 🔎 واجهة البحث والـ Pagination
# =========================================================

def build_episodes_markup(series_name, episodes, page=0, series_id=None):
    start = page * EPISODES_PER_PAGE
    end = start + EPISODES_PER_PAGE
    current = episodes[start:end]

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📂 كل الحلقات", callback_data="ep:episodes:0")
    )

    for ep_id, ep_name in current:
        clean = ep_name
        if clean.startswith("[") and "](" in clean:
            clean = clean.split("](")[0][1:]

        ep_num = extract_episode(clean)
        text = format_button_text(
            title=clean,
            episode=ep_num,
            quality=extract_quality(clean) or "HD"
        )
        markup.add(
            InlineKeyboardButton(text=text, callback_data=f"ep:num:{ep_num}")
        )

    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"ep:page:{page-1}"))
    if end < len(episodes):
        nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"ep:page:{page+1}"))

    if nav:
        markup.row(*nav)

    return markup


def show_episodes(message):
    query_raw = message.text.strip()
    series_query, wanted_episode = smart_parse_query(query_raw)

    # بحث صاروخي فوري
    matches = fast_search_media(series_query, media_type="series")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    matched = []
    detected_series_name = None
    detected_series_id = None

    if matches:
        detected_series_name, detected_series_id = matches[0]
        cursor.execute(
            """
            SELECT id, episode_name, season, episode
            FROM episodes
            WHERE (series_id = ? OR series_name = ?)
            ORDER BY season ASC, episode ASC, id ASC
            """,
            (detected_series_id, detected_series_name)
        )
        for ep_id, ep_name, s_num, e_num in cursor.fetchall():
            if wanted_episode and e_num != wanted_episode:
                continue
            matched.append((ep_id, ep_name))

    if not matched:
        # فحص اللينكات السريع
        cursor.execute("SELECT link_id, series_name FROM links WHERE series_name LIKE ? LIMIT 5", (f"%{series_query}%",))
        links = cursor.fetchall()
        if links:
            markup = InlineKeyboardMarkup()
            for link_id, s_name in links:
                markup.add(
                    InlineKeyboardButton(
                        f"📂 {s_name}",
                        url=f"https://t.me/{BOT_USERNAME}?start=series_{link_id}"
                    )
                )
            bot.send_message(
                message.chat.id,
                "🎬 *هل تقصد هذا المسلسل؟*",
                reply_markup=markup,
                parse_mode="Markdown"
            )
            conn.close()
            return

    if not matched or not detected_series_name:
        conn.close()
        bot.send_message(message.chat.id, "ممكن يكون المسلسل ده مش موجود 🥺")
        return

    if not detected_series_id:
        detected_series_id = get_or_create_series_id(detected_series_name, "series")

    # حفظ سجل البحث
    try:
        cursor.execute(
            "INSERT INTO search_history (user_id, query, search_date, created_at) VALUES (?, ?, ?, ?)",
            (message.from_user.id, detected_series_name, datetime.now().isoformat(), datetime.now().isoformat())
        )
        conn.commit()
    except Exception:
        pass

    final_series_name = get_series_name_for_caption(detected_series_name) or detected_series_name
    caption_data = get_caption_with_fallback(cursor, final_series_name, media_type="tv")
    conn.close()

    markup = build_episodes_markup(final_series_name, matched, page=0, series_id=detected_series_id)
    photo_id, caption_text = caption_data if caption_data else (None, None)

    if photo_id and caption_text:
        try:
            msg = bot.send_photo(
                message.chat.id, photo_id,
                caption=safe_markdown(caption_text),
                reply_markup=markup, parse_mode="Markdown",
                reply_to_message_id=getattr(message, 'message_id', None)
            )
        except Exception:
            msg = bot.send_message(
                message.chat.id, safe_markdown(caption_text),
                reply_markup=markup, parse_mode="Markdown",
                reply_to_message_id=getattr(message, 'message_id', None)
            )
    elif caption_text:
        msg = bot.send_message(
            message.chat.id, safe_markdown(caption_text),
            reply_markup=markup, parse_mode="Markdown",
            reply_to_message_id=getattr(message, 'message_id', None)
        )
    else:
        msg = bot.send_message(
            message.chat.id, f"🎬 *{safe_markdown(final_series_name)}*",
            reply_markup=markup, parse_mode="Markdown",
            reply_to_message_id=getattr(message, 'message_id', None)
        )

    user_sessions[msg.message_id] = {
        "series_id": detected_series_id,
        "series_name": final_series_name,
        "episodes": matched,
        "all_episodes": matched,
        "page": 0
    }


def build_movies_markup(results, page=0):
    markup = InlineKeyboardMarkup(row_width=1)
    total_pages = max(1, (len(results) + MOVIES_PER_PAGE - 1) // MOVIES_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * MOVIES_PER_PAGE
    end = start + MOVIES_PER_PAGE
    page_results = results[start:end]

    for ep_id, name, quality in page_results:
        markup.add(
            InlineKeyboardButton(
                f"🎞 {name} — {quality}",
                url=f"https://t.me/{BOT_USERNAME}?start=episode_{ep_id}"
            )
        )

    navigation_buttons = []
    if page > 0:
        navigation_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"moviepg:{page - 1}"))
    if page < total_pages - 1:
        navigation_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"moviepg:{page + 1}"))

    if navigation_buttons:
        markup.row(*navigation_buttons)

    markup.add(InlineKeyboardButton(f"📄 صفحة {page + 1} من {total_pages}", callback_data="moviepg:noop"))
    return markup


def show_movies(message):
    user_id = message.from_user.id

    if message.chat.type == "private":
        if not private_search_mode.get(user_id):
            return
        private_search_mode.pop(user_id, None)

    query_raw = message.text.strip()

    # بحث صاروخي فوري للأفلام
    matches = fast_search_media(query_raw, media_type="movie")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    results = []
    final_movie_name = None

    if matches:
        final_movie_name, _ = matches[0]
        cursor.execute(
            "SELECT id, series_name, quality FROM episodes WHERE series_name = ? ORDER BY id DESC",
            (final_movie_name,)
        )
        for ep_id, s_name, q in cursor.fetchall():
            results.append((ep_id, s_name, q or "HD"))
    else:
        cursor.execute("SELECT id, series_name, quality FROM episodes WHERE media_type = 'movie' LIMIT 100")
        for ep_id, series_name, quality in cursor.fetchall():
            if word_match(query_raw, series_name):
                results.append((ep_id, series_name, quality or "HD"))
                final_movie_name = series_name

    if not results or not final_movie_name:
        conn.close()
        bot.send_message(message.chat.id, "قد يكون الفيلم غير موجود في البوت 🥺")
        return

    try:
        cursor.execute(
            "INSERT INTO search_history (user_id, query, search_date, created_at) VALUES (?, ?, ?, ?)",
            (message.from_user.id, final_movie_name, datetime.now().isoformat(), datetime.now().isoformat())
        )
        conn.commit()
    except Exception as e:
        print("SEARCH HISTORY ERROR:", repr(e))

    caption_data = get_caption_with_fallback(cursor, final_movie_name, media_type="movie")
    conn.close()

    photo_id, caption_text = caption_data if caption_data else (None, None)
    page = 0
    markup = build_movies_markup(results, page)

    sent_message = None
    if photo_id and caption_text:
        try:
            sent_message = bot.send_photo(
                message.chat.id, photo_id,
                caption=safe_markdown(caption_text),
                reply_markup=markup, parse_mode="Markdown",
                reply_to_message_id=getattr(message, 'message_id', None)
            )
        except Exception:
            pass

    if sent_message is None and caption_text:
        sent_message = bot.send_message(
            message.chat.id, safe_markdown(caption_text),
            reply_markup=markup, parse_mode="Markdown",
            reply_to_message_id=getattr(message, 'message_id', None)
        )

    if sent_message is None:
        sent_message = bot.send_message(
            message.chat.id, f"🎬 *{safe_markdown(final_movie_name)}*",
            reply_markup=markup, parse_mode="Markdown",
            reply_to_message_id=getattr(message, 'message_id', None)
        )

    movie_sessions[sent_message.message_id] = {
        "chat_id": message.chat.id,
        "results": results,
        "page": 0
    }


@bot.callback_query_handler(func=lambda call: call.data.startswith("moviepg:"))
def movies_pagination_callback(call):
    try:
        value = call.data.split(":")[1]
        if value == "noop":
            bot.answer_callback_query(call.id)
            return

        new_page = int(value)
        message_id = call.message.message_id
        session = movie_sessions.get(message_id)

        if not session:
            bot.answer_callback_query(call.id, "❌ الصفحة انتهت، اعمل بحث جديد.")
            return

        session["page"] = new_page
        markup = build_movies_markup(session["results"], new_page)
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=message_id,
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        print("MOVIES PAGINATION ERROR:", repr(e))


@bot.message_handler(func=lambda message: message.chat.type in ["group", "supergroup"] and not message.text.startswith("/"))
def choose_type(message):
    query = message.text.strip()
    search_sessions[message.from_user.id] = {
        "query": query,
        "message_id": message.message_id
    }

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(text="📺 أفلام", callback_data="type_movie"),
        types.InlineKeyboardButton(text="🎬 مسلسلات", callback_data="type_series")
    )

    text = f"🔍 <b>جاري البحث عن:</b> <code>{html.escape(query)}</code>\n\n<b> اختار النوع اللي بتدور عليه:</b> 👇"
    bot.reply_to(message, text, parse_mode="HTML", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data in ["type_movie", "type_series"])
def handle_type(call):
    user_id = call.from_user.id
    data = search_sessions.get(user_id)

    if not data:
        bot.send_message(call.message.chat.id, "❌ مفيش بحث محفوظ")
        return

    query = data.get("query")
    user_message_id = data.get("message_id")

    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

    real_user_message = SimpleNamespace(
        chat=call.message.chat,
        from_user=call.from_user,
        text=query,
        message_id=user_message_id
    )

    if call.data == "type_series":
        show_episodes(real_user_message)
    else:
        show_movies(real_user_message)

    search_sessions.pop(user_id, None)


def send_episodes_list(chat_id, message_id, series_name, episodes, page=0):
    session = user_sessions.get(message_id)
    if not session:
        return

    seasons = sorted({
        extract_season(name)
        for _, name in episodes
        if extract_season(name) is not None
    })

    session["seasons"] = seasons
    session["all_episodes"] = episodes

    max_page = (len(episodes) - 1) // EPISODES_PER_PAGE
    page = max(0, min(page, max_page))
    session["page"] = page

    start = page * EPISODES_PER_PAGE
    end = start + EPISODES_PER_PAGE
    current = episodes[start:end]

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🔄 ارتبلك الحلقات يخويا", callback_data="ep:sort"),
        InlineKeyboardButton("🆕 🔥 الحلقة الجديدة يصحبي", callback_data="ep:latest")
    )
    markup.add(
        InlineKeyboardButton("⚙️ اختر جودة تسمع بيها", callback_data="ep:qualities")
    )
    markup.add(
        InlineKeyboardButton("❤️ المفضلة", callback_data="ep:fav")
    )
    markup.add(
        InlineKeyboardButton("📥 إرسال الكل", callback_data="ep:sendall")
    )

    top = []
    if len(seasons) > 1:
        top.append(InlineKeyboardButton("🎬 المواسم", callback_data="ep:seasons:0"))
    top.append(InlineKeyboardButton("📂 الحلقات", callback_data="ep:episodes:0"))
    markup.add(*top)

    for ep_id, ep_name in current:
        clean = ep_name
        if clean.startswith("[") and "](" in clean:
            clean = clean.split("](")[0][1:]

        ep_num = extract_episode(clean)
        text = format_button_text(
            title=clean,
            episode=ep_num,
            quality=extract_quality(clean) or "HD"
        )
        markup.add(
            InlineKeyboardButton(text=text, callback_data=f"ep:num:{ep_num}")
        )

    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"ep:page:{page-1}"))
    if end < len(episodes):
        nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"ep:page:{page+1}"))

    if nav:
        markup.add(*nav)

    bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=markup)


def handle_favorite(call, series_name):
    user_id = call.from_user.id
    series_id = get_or_create_series_id(series_name, "series")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM favorites WHERE user_id=? AND (series_name=? OR series_id=?)", (user_id, series_name, series_id))
    exists = cursor.fetchone()

    if exists:
        cursor.execute("DELETE FROM favorites WHERE user_id=? AND (series_name=? OR series_id=?)", (user_id, series_name, series_id))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "💔 تمت الإزالة من المفضلة")
    else:
        cursor.execute("INSERT INTO favorites (user_id, series_id, series_name) VALUES (?, ?, ?)", (user_id, series_id, series_name))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "❤️ تمت الإضافة للمفضلة")


# =========================================================
# 📥 ميزة إرسال الكل الذكية والمضبوطة عددياً بالكامل
# =========================================================

def show_sendall_ranges(call, session, series_name):
    """
    حساب عدد حلقات المسلسل بدقة متناهية بناءً على الموسم ورقم الحلقة،
    مع معاملة جودة HD والجودات كعنصر طبيعي دون استبعاد أو لخبطة الحساب.
    """
    series_id = session.get("series_id") or get_or_create_series_id(series_name, "series")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, file_id, episode_name, season, episode, quality
        FROM episodes
        WHERE (series_id = ? OR series_name = ?)
        ORDER BY season ASC, episode ASC, id ASC
        """,
        (series_id, series_name)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        bot.answer_callback_query(call.id, "❌ مفيش حلقات متاحة للإرسال", show_alert=True)
        return

    total = len(rows)
    markup = InlineKeyboardMarkup(row_width=2)

    # تقسيم الحلقات في مجموعات كل منها 10 حلقات
    for offset in range(0, total, 10):
        first = offset + 1
        last = min(offset + 10, total)
        payload = f"bulk_{series_id}_{first}_{last}"

        markup.add(
            InlineKeyboardButton(
                f"📦 الحلقات {first} - {last} (من {total})",
                url=f"https://t.me/{BOT_USERNAME}?start={payload}"
            )
        )

    markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="ep:back"))
    bot.edit_message_reply_markup(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("ep:"))
def episodes_callback(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    parts = call.data.split(":")
    if len(parts) < 2:
        return

    action = parts[1]
    value = parts[2] if len(parts) > 2 else None

    session = user_sessions.get(msg_id)
    if not session:
        bot.send_message(chat_id, "اعمل بحث جديد كفاية ضغط ع الأزرار ❌")
        return

    episodes = session["episodes"]
    series_name = session["series_name"]
    page = session.get("page", 0)

    # إرسال الكل المباشر والمظبوط
    if action == "sendall":
        return show_sendall_ranges(call, session, series_name)

    if action == "episodes":
        page = int(value or 0)
        nums = sorted({extract_episode(name) for _, name in episodes if extract_episode(name) is not None})
        start = page * EP_NUMBERS_PER_PAGE
        end = start + EP_NUMBERS_PER_PAGE

        markup = InlineKeyboardMarkup(row_width=4)
        for num in nums[start:end]:
            markup.add(InlineKeyboardButton(f"الحلقة {num}", callback_data=f"ep:num:{num}"))

        nav = []
        if start > 0:
            nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"ep:episodes:{page-1}"))
        if end < len(nums):
            nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"ep:episodes:{page+1}"))
        nav.append(InlineKeyboardButton("🔙 رجوع", callback_data="ep:back"))

        markup.add(*nav)
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=markup)
        return

    if action == "seasons":
        page = int(value or 0)
        seasons = session.get("seasons", [])
        start = page * 8
        end = start + 8

        markup = InlineKeyboardMarkup(row_width=4)
        for s in seasons[start:end]:
            markup.add(InlineKeyboardButton(f"الموسم {s}", callback_data=f"ep:season:{s}"))

        nav = []
        if start > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"ep:seasons:{page-1}"))
        if end < len(seasons):
            nav.append(InlineKeyboardButton("➡️", callback_data=f"ep:seasons:{page+1}"))
        nav.append(InlineKeyboardButton("🔙 رجوع", callback_data="ep:back"))

        markup.add(*nav)
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=markup)
        return

    if action == "season":
        season = int(value)
        filtered = [(eid, name) for eid, name in episodes if extract_season(name) == season]
        session["episodes"] = filtered
        session["page"] = 0
        send_episodes_list(chat_id, msg_id, series_name, filtered, 0)
        return

    if action == "num":
        ep_num = int(value)
        items = [(eid, name) for eid, name in episodes if extract_episode(name) == ep_num]
        markup = InlineKeyboardMarkup(row_width=2)
        for eid, name in items:
            clean = name
            if clean.startswith("[") and "](" in clean:
                clean = clean.split("](")[0][1:]
            q = extract_quality(clean) or "HD"
            markup.add(
                InlineKeyboardButton(f"🎞 {q}", url=f"https://t.me/{BOT_USERNAME}?start=episode_{eid}")
            )
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="ep:episodes:0"))
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=markup)
        return

    if action == "page":
        page = int(value)
        session["page"] = page
        send_episodes_list(chat_id, msg_id, series_name, episodes, page)
        return

    if action == "back":
        send_episodes_list(chat_id, msg_id, series_name, session["episodes"], session.get("page", 0))
        return

    if action == "sort":
        eps = sorted(session["episodes"], key=lambda x: extract_episode(x[1]) or 0)
        session["episodes"] = eps
        send_episodes_list(chat_id, msg_id, series_name, eps, 0)
        return

    if action == "latest":
        all_eps = session.get("all_episodes", [])
        if not all_eps:
            bot.answer_callback_query(call.id, "❌ لا توجد حلقات")
            return
        latest = max(all_eps, key=lambda x: extract_episode(x[1]) or 0)
        send_episodes_list(chat_id, msg_id, series_name, [latest], 0)
        return

    if action == "qualities":
        all_eps = session.get("all_episodes", [])
        qualities = sorted({normalize_quality(extract_quality(name) or "HD") for _, name in all_eps})
        markup = InlineKeyboardMarkup()
        for q in qualities:
            markup.add(InlineKeyboardButton(f"🎞 {q}", callback_data=f"ep:quality:{q}"))
        markup.add(InlineKeyboardButton("🔙 رجوع", callback_data="ep:back"))
        bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=markup)
        return

    if action == "quality":
        q = value
        all_eps = session.get("all_episodes", [])
        filtered = [(eid, name) for eid, name in all_eps if (extract_quality(name) or "HD") == q]
        session["episodes"] = filtered
        send_episodes_list(chat_id, msg_id, series_name, filtered, 0)
        return

    if action == "fav":
        handle_favorite(call, series_name)
        return


# =========================================================
# 👑 أوامر الأدمن ولوحة القيادة
# =========================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_router(call):
    if call.from_user.id != ADMIN_ID:
        return

    action = call.data.replace("admin_", "")

    if action == "send":
        start_broadcast(call.message)
    elif action == "block":
        msg = bot.send_message(call.message.chat.id, "🚫 ابعت ايدي المستخدم اللي عايز تحظره")
        bot.register_next_step_handler(msg, block_user)
    elif action == "unblock":
        msg = bot.send_message(call.message.chat.id, "✅ ابعت ايدي المستخدم اللي عايز تفك حظره")
        bot.register_next_step_handler(msg, unblock_user)
    elif action == "remove":
        msg = bot.send_message(call.message.chat.id, "➖ ابعت ايدي المستخدم لحذف اشتراكه")
        bot.register_next_step_handler(msg, remove_subscription)
    elif action == "clearcache":
        user_sessions.clear()
        series_sessions.clear()
        search_sessions.clear()
        confirm_sessions.clear()
        SERIES_CACHE.clear()
        MOVIES_CACHE.clear()
        FAST_SEARCH_CACHE.clear()
        USER_TRANSFERS.clear()
        bot.send_message(call.message.chat.id, "✅ تم مسح الكاش بالكامل")
    elif action == "delete":
        delete_menu(call.message)
    elif action == "link":
        make_link(call.message)
    elif action == "deletelink":
        msg = bot.send_message(call.message.chat.id, "❌ ابعت اسم المسلسل لحذف اللينك")
        bot.register_next_step_handler(msg, delete_link)
    elif action == "startnotify":
        start_notify(call.message)
    elif action == "stopnotify":
        stop_notify(call.message)
    elif action == "stats":
        stats_command(call.message)
    elif action == "back_control":
        bot.answer_callback_query(call.id, "👑 رجعناك للقيادة")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        send_admin_dashboard(call.message.chat.id, call.from_user.first_name or "قائد")
    else:
        bot.answer_callback_query(call.id, "❌ أمر غير معروف")


def block_user(message):
    try:
        uid = int(message.text.strip())
        BLOCKED_USERS.add(uid)
        bot.reply_to(message, f"🚫 تم حظر المستخدم {uid}")
    except Exception:
        bot.reply_to(message, "❌ آيدي غير صحيح")


def unblock_user(message):
    try:
        user_id = int(message.text.strip())
        BLOCKED_USERS.discard(user_id)
        bot.send_message(message.chat.id, f"✅ تم فك الحظر عن {user_id}")
    except Exception:
        bot.send_message(message.chat.id, "❌ ايدي غير صحيح")


def remove_subscription(message):
    try:
        user_id = message.text.strip()
        if not user_id.isdigit():
            bot.send_message(message.chat.id, "❌ الـ ID لازم يكون أرقام بس.")
            return

        user_id = int(user_id)
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT end_date FROM subscriptions WHERE user_id = ?", (user_id,))
        subscription = cursor.fetchone()

        if not subscription:
            conn.close()
            bot.send_message(message.chat.id, f"❌ مفيش اشتراك للمستخدم:\n`{user_id}`", parse_mode="Markdown")
            return

        cursor.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

        try:
            bot.send_message(
                user_id,
                "الإدارة قررت إنهاء اشتراكك VIP.\n🔒 اشتراكك اتلغى، والمحتوى المدفوع مش متاح ليك حالياً."
            )
        except Exception:
            pass

        bot.send_message(message.chat.id, f"✅ تم إلغاء اشتراك المستخدم `{user_id}` بنجاح 👑", parse_mode="Markdown")
    except Exception as e:
        print("❌ REMOVE SUBSCRIPTION ERROR:", repr(e))
        bot.send_message(message.chat.id, "❌ حصل خطأ أثناء إلغاء الاشتراك.")


@bot.message_handler(commands=['control'])
def admin_control(message):
    if message.from_user.id != ADMIN_ID:
        return
    send_admin_dashboard(message.chat.id, message.from_user.first_name or "قائد")


def send_admin_dashboard(chat_id, admin_name="قائد"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM episodes")
    episodes_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM links")
    links_count = cursor.fetchone()[0]

    cursor.execute("SELECT user_id, end_date FROM subscriptions")
    rows = cursor.fetchall()
    conn.close()

    egypt_tz = ZoneInfo("Africa/Cairo")
    now = datetime.now(egypt_tz)

    active = 0
    expired = 0
    for user_id, end in rows:
        try:
            end_date = datetime.fromisoformat(end)
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=egypt_tz)
            else:
                end_date = end_date.astimezone(egypt_tz)

            if end_date > now:
                active += 1
            else:
                expired += 1
        except Exception:
            pass

    text = f"""
╔══════════════════════════╗
        👑 <b>لوحة القيادة</b>
╚══════════════════════════╝

🔥 أهلاً بيك يا قائد <b>{admin_name}</b>

━━━━━━━━━━━━━━━━━━━━

📊 <b>إحصائيات البوت</b>

👤 المستخدمين
└─ <code>{users_count}</code> مستخدم

🎞 المحتوى
└─ <code>{episodes_count}</code> فيديو

🔗 اللينكات
└─ <code>{links_count}</code> لينك

━━━━━━━━━━━━━━━━━━━━

💎 <b>الاشتراكات</b>

✅ النشطين
└─ <code>{active}</code> مشترك

❌ المنتهيين
└─ <code>{expired}</code> مشترك

━━━━━━━━━━━━━━━━━━━━

🇪🇬 <b>توقيت القاهرة</b>
📅 <code>{now.strftime("%Y-%m-%d")}</code>
🕐 <code>{now.strftime("%H:%M:%S")}</code>

━━━━━━━━━━━━━━━━━━━━
        ⚡ <b>مركز التحكم الرئيسي</b>
━━━━━━━━━━━━━━━━━━━━
"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📢 إذاعة", callback_data="admin_send"),
        types.InlineKeyboardButton("🗑 حذف", callback_data="admin_delete")
    )
    markup.add(
        types.InlineKeyboardButton("🚫 Block", callback_data="admin_block"),
        types.InlineKeyboardButton("✅ Unblock", callback_data="admin_unblock")
    )
    markup.add(
        types.InlineKeyboardButton("➖ حذف اشتراك", callback_data="admin_remove"),
        types.InlineKeyboardButton("🧹 مسح الكاش", callback_data="admin_clearcache")
    )
    markup.add(
        types.InlineKeyboardButton("🔗 إنشاء لينك", callback_data="admin_link"),
        types.InlineKeyboardButton("❌ حذف لينك", callback_data="admin_deletelink")
    )
    markup.add(
        types.InlineKeyboardButton("✅ المشتركين النشطين", callback_data="show_active_0"),
        types.InlineKeyboardButton("❌ المنتهيين", callback_data="show_expired_0")
    )

    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")


PAGE_SIZE = 10

@bot.callback_query_handler(func=lambda call: call.data.startswith("show_active_"))
def show_active(call):
    if call.from_user.id != ADMIN_ID:
        return

    page = int(call.data.split("_")[-1])
    egypt_tz = ZoneInfo("Africa/Cairo")
    now = datetime.now(egypt_tz)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, end_date FROM subscriptions ORDER BY end_date DESC")
    rows = cursor.fetchall()
    conn.close()

    active_users = []
    for user_id, end_date in rows:
        try:
            end_dt = datetime.fromisoformat(end_date)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=egypt_tz)
            else:
                end_dt = end_dt.astimezone(egypt_tz)

            if end_dt > now:
                active_users.append((user_id, end_dt))
        except Exception:
            pass

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    users_page = active_users[start:end]
    total_pages = max(1, (len(active_users) + PAGE_SIZE - 1) // PAGE_SIZE)

    text = (
        "╔══════════════════════════╗\n"
        "        👑 <b>المشتركين النشطين</b>\n"
        "╚══════════════════════════╝\n\n"
        f"💎 <b>إجمالي المشتركين:</b> <code>{len(active_users)}</code>\n"
        f"📄 <b>الصفحة:</b> <code>{page + 1} / {total_pages}</code>\n"
        f"🇪🇬 <b>توقيت القاهرة:</b> <code>{now.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    for index, (user_id, end_dt) in enumerate(users_page, start=start + 1):
        try:
            user = bot.get_chat(user_id)
            name = user.first_name or "غير معروف"
            username = f"@{user.username}" if user.username else "لا يوجد"
        except Exception:
            name, username = "غير معروف", "غير معروف"

        remaining = end_dt - now
        total_seconds = max(0, int(remaining.total_seconds()))
        days = total_seconds // 86400
        total_seconds %= 86400
        hours = total_seconds // 3600
        total_seconds %= 3600
        minutes = total_seconds // 60
        seconds = total_seconds % 60

        text += (
            f"👤 <b>#{index} {name}</b>\n"
            f"🆔 <code>{user_id}</code>\n"
            f"📛 {username}\n"
            f"⏳ <b>المتبقي:</b> {days} يوم و {hours} ساعة و {minutes} دقيقة\n"
            f"📅 <b>ينتهي في:</b> <code>{end_dt.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
        )

    markup = types.InlineKeyboardMarkup(row_width=2)
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton("⬅️ السابق", callback_data=f"show_active_{page - 1}"))
    if end < len(active_users):
        nav.append(types.InlineKeyboardButton("التالي ➡️", callback_data=f"show_active_{page + 1}"))

    if nav:
        markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🏠 لوحة القيادة", callback_data="admin_back_control"))

    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


@bot.callback_query_handler(func=lambda call: call.data.startswith("show_expired_"))
def show_expired(call):
    if call.from_user.id != ADMIN_ID:
        return

    page = int(call.data.split("_")[-1])
    egypt_tz = ZoneInfo("Africa/Cairo")
    now = datetime.now(egypt_tz)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, end_date FROM subscriptions ORDER BY end_date DESC")
    rows = cursor.fetchall()
    conn.close()

    expired_users = []
    for user_id, end_date in rows:
        try:
            end_dt = datetime.fromisoformat(end_date)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=egypt_tz)
            else:
                end_dt = end_dt.astimezone(egypt_tz)

            if end_dt <= now:
                expired_users.append((user_id, end_dt))
        except Exception:
            pass

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    users_page = expired_users[start:end]
    total_pages = max(1, (len(expired_users) + PAGE_SIZE - 1) // PAGE_SIZE)

    text = (
        "╔══════════════════════════╗\n"
        "       ❌ <b>الاشتراكات المنتهية</b>\n"
        "╚══════════════════════════╝\n\n"
        f"📊 <b>إجمالي المنتهيين:</b> <code>{len(expired_users)}</code>\n"
        f"📄 <b>الصفحة:</b> <code>{page + 1} / {total_pages}</code>\n"
        f"🇪🇬 <b>الوقت الحالي:</b> <code>{now.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    for index, (user_id, end_dt) in enumerate(users_page, start=start + 1):
        try:
            user = bot.get_chat(user_id)
            name = user.first_name or "غير معروف"
            username = f"@{user.username}" if user.username else "لا يوجد"
        except Exception:
            name, username = "غير معروف", "غير معروف"

        text += (
            f"👤 <b>#{index} {name}</b>\n"
            f"🆔 <code>{user_id}</code>\n"
            f"📛 {username}\n"
            f"🔴 <b>انتهى الاشتراك في:</b> <code>{end_dt.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
        )

    markup = types.InlineKeyboardMarkup(row_width=2)
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton("⬅️ السابق", callback_data=f"show_expired_{page - 1}"))
    if end < len(expired_users):
        nav.append(types.InlineKeyboardButton("التالي ➡️", callback_data=f"show_expired_{page + 1}"))

    if nav:
        markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🏠 لوحة القيادة", callback_data="admin_back_control"))

    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


@bot.message_handler(commands=['stats'])
def stats_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    text = build_stats_text(DB_NAME)
    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=['stop_notify'])
def stop_notify(message):
    if message.from_user.id != ADMIN_ID:
        return
    global NOTIFICATIONS_ENABLED
    NOTIFICATIONS_ENABLED = False
    bot.reply_to(message, "🔕 تم إيقاف الإشعارات")


@bot.message_handler(commands=['start_notify'])
def start_notify(message):
    if message.from_user.id != ADMIN_ID:
        return
    global NOTIFICATIONS_ENABLED
    NOTIFICATIONS_ENABLED = True
    bot.reply_to(message, "🔔 تم تشغيل الإشعارات")


def start_broadcast(message):
    if message.chat.id == ADMIN_ID:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("❌ إلغاء الإذاعة")
        bot.send_message(
            ADMIN_ID,
            "📢 ابعت دلوقتي أي حاجة: نص، صورة، استيكر، أو فيديو للإذاعة لجميع المستخدمين:",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, broadcast_to_all)


def broadcast_to_all(message):
    if message.text == "❌ إلغاء الإذاعة":
        bot.send_message(ADMIN_ID, "✅ تم إلغاء الإذاعة يصحبي.", reply_markup=types.ReplyKeyboardRemove())
        return

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        conn.close()

        sent = 0
        failed = 0
        bot.send_message(ADMIN_ID, "🚀 بدأت عملية الإذاعة..")

        for (user_id,) in users:
            if user_id == ADMIN_ID:
                continue
            try:
                bot.copy_message(chat_id=user_id, from_chat_id=ADMIN_ID, message_id=message.message_id)
                sent += 1
                if sent % 20 == 0:
                    time.sleep(1)
            except Exception:
                failed += 1

        bot.send_message(
            ADMIN_ID,
            f"📊 **تقرير الإذاعة النهائي**\n\n"
            f"✅ تم الإرسال بنجاح: {sent}\n"
            f"❌ فشل: {failed}\n"
            f"📦 الإجمالي: {sent + failed}",
            parse_mode="Markdown",
            reply_markup=types.ReplyKeyboardRemove()
        )
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ خطأ في الإذاعة: {str(e)}")


def make_link(msg):
    bot.send_message(msg.chat.id, "✔️ ابعت اسم المسلسل اللي عايز تعمل له لينك ثابت:")
    bot.register_next_step_handler(msg, save_series_link)


def save_series_link(msg):
    series_name = msg.text.strip()
    series_id = get_or_create_series_id(series_name, "series")
    link_id = str(uuid.uuid4())[:8]

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO links (series_id, series_name, link_id) VALUES (?, ?, ?)", (series_id, series_name, link_id))
    cursor.execute("UPDATE episodes SET link_id=? WHERE series_name=? OR series_id=?", (link_id, series_name, series_id))
    conn.commit()
    conn.close()

    link = f"https://t.me/{BOT_USERNAME}?start=series_{link_id}"
    bot.send_message(
        msg.chat.id,
        f"✅ تم إنشاء لينك المسلسل بنجاح\n\n🎬 {series_name}\n\n🔗 اللينك:\n{link}"
    )


def delete_link(message):
    if message.chat.id != ADMIN_ID:
        return

    query = " ".join(message.text.split()[1:]).strip() if len(message.text.split()) > 1 else message.text.strip()
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id, series_name FROM links")
    rows = cur.fetchall()
    conn.close()

    matched = [(lid, sname) for lid, sname in rows if word_match(query, sname)]
    if not matched:
        bot.reply_to(message, "❌ مفيش أي لينك مطابق للاسم ده")
        return

    if len(matched) == 1:
        link_id, series_name = matched[0]
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("DELETE FROM links WHERE id=?", (link_id,))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ تم حذف لينك المسلسل:\n🎬 {series_name}")
        return

    markup = InlineKeyboardMarkup()
    for link_id, series_name in matched:
        markup.add(InlineKeyboardButton(f"🗑 حذف: {series_name}", callback_data=f"confirm_delete_link_{link_id}"))
    bot.reply_to(message, "⚠️ فيه أكتر من لينك مطابق، اختر أحدهم:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_delete_link_"))
def confirm_delete_link(call):
    if call.message.chat.id != ADMIN_ID:
        return
    link_id = call.data.split("confirm_delete_link_")[1]
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM links WHERE id=?", (link_id,))
    conn.commit()
    conn.close()
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    bot.send_message(call.message.chat.id, "✅ تم حذف اللينك بنجاح")
    bot.answer_callback_query(call.id)


def delete_menu(message):
    if message.chat.id != ADMIN_ID:
        return
    msg = bot.send_message(ADMIN_ID, "🗑 اختر ما تريد حذفه:\n1️⃣ اكتب: حلقة\n2️⃣ اكتب: مسلسل")
    bot.register_next_step_handler(msg, delete_choice)


def delete_choice(message):
    if message.chat.id != ADMIN_ID:
        return
    choice = message.text.strip()
    if choice == "حلقة":
        msg = bot.send_message(ADMIN_ID, "🔹 أرسل اسم الحلقة:")
        bot.register_next_step_handler(msg, delete_episode_by_name)
    elif choice == "مسلسل":
        msg = bot.send_message(ADMIN_ID, "🔹 أرسل اسم المسلسل:")
        bot.register_next_step_handler(msg, delete_series_by_name)
    else:
        bot.send_message(ADMIN_ID, "❌ اختيار غير صحيح.")


def delete_episode_by_name(message):
    if message.chat.id != ADMIN_ID:
        return
    query = message.text.strip()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM episodes WHERE episode_name LIKE ?", (f"%{query}%",))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted:
        bot.send_message(ADMIN_ID, f"✅ تم حذف {deleted} حلقة تطابق:\n{query}")
    else:
        bot.send_message(ADMIN_ID, "❌ الحلقة غير موجودة.")


def delete_series_by_name(message):
    if message.chat.id != ADMIN_ID:
        return
    raw = message.text.strip()
    search = normalize_series_name(raw)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT series_name FROM episodes")
    rows = cursor.fetchall()

    matched_series = {s_name for (s_name,) in rows if normalize_series_name(s_name).find(search) != -1}
    if not matched_series:
        conn.close()
        bot.send_message(ADMIN_ID, "❌ المسلسل غير موجود.")
        return

    total_deleted = 0
    for s in matched_series:
        cursor.execute("DELETE FROM episodes WHERE series_name = ?", (s,))
        total_deleted += cursor.rowcount

    conn.commit()
    conn.close()
    bot.send_message(ADMIN_ID, f"✅ تم حذف المسلسل بنجاح\n🎬 الاسم: {raw}\n🗑 عدد الحلقات: {total_deleted}")


def generate_code(length=10):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


@bot.message_handler(commands=['renew'])
def create_sub_link(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ انت مش الأدمن")
        return

    try:
        text = message.text.split()[1]
        months = 12 if text in ["سنه", "سنة"] else int(text)
    except Exception:
        bot.reply_to(message, "❌ استخدم كالتالي:\n/renew 1\n/renew 3\n/renew 6\n/renew 12")
        return

    code = generate_code()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO subscription_codes (code, months, used) VALUES (?, ?, 0)", (code, months))
    conn.commit()
    conn.close()

    link = f"https://t.me/{BOT_USERNAME}?start=sub_{code}"
    bot.reply_to(message, f"🔥 تم إنشاء رابط اشتراك\n\n📦 المدة: {months} شهر\n🔗 اللينك:\n{link}\n\n⚠️ يستخدم مرة واحدة فقط")


@bot.message_handler(commands=['myplan'])
def myplan_command(message):
    user = message.from_user
    user_id = user.id
    egypt_tz = ZoneInfo("Africa/Cairo")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT start_date, end_date FROM subscriptions WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        bot.send_message(message.chat.id, "❌ لا يوجد لديك اشتراك مفعل")
        return

    start_date = datetime.fromisoformat(row[0])
    end_date = datetime.fromisoformat(row[1])

    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=egypt_tz)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=egypt_tz)

    now = datetime.now(egypt_tz)
    remaining = end_date - now

    if remaining.total_seconds() <= 0:
        status = "❌ منتهي"
        remaining_text = "0 يوم / 0 ساعة"
    else:
        status = "✅ فعال"
        total_seconds = int(remaining.total_seconds())
        days = total_seconds // 86400
        total_seconds %= 86400
        hours = total_seconds // 3600
        total_seconds %= 3600
        minutes = total_seconds // 60
        remaining_text = f"{days} يوم / {hours} ساعة / {minutes} دقيقة"

    text = f"""
💎 *بيانات اشتراكك*

👤 الاسم: {user.first_name}
🆔 ID: `{user_id}`
━━━━━━━━━━━━━━
📅 *بداية الاشتراك:* {start_date.strftime("%Y-%m-%d %H:%M")}
⏳ *نهاية الاشتراك:* {end_date.strftime("%Y-%m-%d %H:%M")}
━━━━━━━━━━━━━━
📊 الحالة: {status}
⌛ *المتبقي:* {remaining_text}
🇪🇬 توقيت القاهرة
"""
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text and m.text.startswith('/favorites'))
def favorites_command(message):
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT series_name FROM favorites WHERE user_id=?", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        bot.send_message(message.chat.id, "❌ لا توجد مفضلة")
        return

    text = "❤️ المفضلة الخاصة بك:\n\n" + "\n".join([f"• {r[0]}" for r in rows])
    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=['tt'])
def history_command(message):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT query, COUNT(*) as cnt
        FROM search_history
        GROUP BY query
        ORDER BY cnt DESC
        LIMIT 10
    """)
    top = cursor.fetchall()
    conn.close()

    if not top:
        bot.send_message(message.chat.id, "📭 مفيش سجل بحث")
        return

    trend_sessions[message.chat.id] = [q for q, _ in top]
    markup = InlineKeyboardMarkup(row_width=1)
    for idx, (query, cnt) in enumerate(top):
        markup.add(InlineKeyboardButton(f"🔥 {query} ({cnt})", callback_data=f"trend:{idx}"))

    bot.send_message(message.chat.id, "🔥 الأكثر بحثاً:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("trend:"))
def trend_callback(call):
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    idx = int(call.data.replace("trend:", ""))
    queries = trend_sessions.get(call.message.chat.id, [])
    if not queries or idx >= len(queries):
        bot.send_message(call.message.chat.id, "❌ اطلب /tt من جديد")
        return

    query = queries[idx]
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT media_type FROM episodes WHERE series_name LIKE ? LIMIT 1", (f"%{query}%",))
    row = cursor.fetchone()
    conn.close()

    media_type = row[0] if row else "series"
    call.message.text = query
    call.message.from_user = call.from_user

    if media_type == "movie":
        show_movies(call.message)
    else:
        show_episodes(call.message)


# =========================================================
# 🚀 المعالج الرئيسي لأمر /start وروابط الـ Deep Links
# =========================================================

@bot.message_handler(commands=['start'])
def send_episode_private(message):
    user = message.from_user
    user_id = user.id
    parts = message.text.split(maxsplit=1)
    payload = parts[1] if len(parts) > 1 else ""

    try:
        bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

    args = message.text.split()

    # تفعيل الاشتراك بالكود
    if len(args) > 1 and args[1].startswith("sub_"):
        code = args[1].replace("sub_", "")
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT months, used FROM subscription_codes WHERE code=?", (code,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            bot.send_message(message.chat.id, "❌ الكود غير صالح")
            return

        months, used = row
        if used == 1:
            conn.close()
            bot.send_message(message.chat.id, "❌ الكود تم استخدامه من قبل")
            return

        start = datetime.now()
        end = start + timedelta(days=months * 30)

        cursor.execute("INSERT OR REPLACE INTO subscriptions VALUES (?, ?, ?, ?)", (user_id, start.isoformat(), end.isoformat(), "VIP"))
        cursor.execute("UPDATE subscription_codes SET used=1, used_by=?, used_at=? WHERE code=?", (user_id, datetime.now().isoformat(), code))
        conn.commit()
        conn.close()

        bot.send_message(
            message.chat.id,
            f"🎉 تم تفعيل اشتراكك بنجاح\n\n👤 الاسم: {user.first_name}\n📅 البداية: {start.strftime('%Y-%m-%d')}\n⏳ النهاية: {end.strftime('%Y-%m-%d')}\n💎 المدة: {months} شهر"
        )
        return

    if len(args) <= 1:
        bot.send_message(message.chat.id, f"Bot series and movie 📺♥️\ncontact programmer @{OWNER_USERNAME}")
        return

    # فحص الاشتراك
    def is_subscribed(uid):
        conn_sub = sqlite3.connect(DB_NAME)
        cur_sub = conn_sub.cursor()
        cur_sub.execute("SELECT end_date FROM subscriptions WHERE user_id=?", (uid,))
        res = cur_sub.fetchone()
        conn_sub.close()
        if not res:
            return False
        try:
            return datetime.now() <= datetime.fromisoformat(res[0])
        except Exception:
            return False

    if not is_subscribed(user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("اضغط لتجديد الاشتراك 🎬", url=f"https://t.me/{OWNER_USERNAME}"))
        bot.send_message(message.chat.id, "❌ اشتراكك منتهي\n\nجدد الاشتراك علشان تقدر تشوف الحلقات والأفلام.", reply_markup=markup)
        return

    raw = args[1]

    # فتح وتصفح المسلسل من البوست الرسمي
    if raw.startswith("show_ser_"):
        sid = raw.replace("show_ser_", "")
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT series_name FROM episodes WHERE series_id = ? LIMIT 1", (sid,))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            fake_msg = SimpleNamespace(
                chat=message.chat,
                from_user=message.from_user,
                text=row[0],
                message_id=message.message_id
            )
            show_episodes(fake_msg)
        else:
            bot.send_message(message.chat.id, "❌ المسلسل غير موجود أو تم حذفه.")
        return

    # فتح وتصفح الفيلم من البوست الرسمي
    if raw.startswith("show_mov_"):
        ep_id = raw.replace("show_mov_", "")
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT series_name, file_id, episode_name FROM episodes WHERE id = ?", (ep_id,))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            fake_msg = SimpleNamespace(
                chat=message.chat,
                from_user=message.from_user,
                text=row[0],
                message_id=message.message_id
            )
            private_search_mode[user_id] = True
            show_movies(fake_msg)
        else:
            bot.send_message(message.chat.id, "❌ الفيلم غير موجود.")
        return

    # الترشيح
    if raw.startswith("rec_"):
        try:
            ep_id = int(raw.replace("rec_", ""))
            handle_recommendation_start(message, ep_id)
        except ValueError:
            bot.send_message(message.chat.id, "رابط الترشيح غير صحيح ❌")
        return

    if raw.startswith(("episode_", "series_", "bulk_")):
        check_transfer(user)

    is_blocked = user_id in BLOCKED_USERS

    # إرسال الكل (Bulk Range) المحسوب بالموسم ورقم الحلقة
    if raw.startswith("bulk_"):
        try:
            parts_bulk = raw.split("_")
            # format: bulk_{series_id}_{first}_{last}
            sid = "_".join(parts_bulk[1:-2])
            first = int(parts_bulk[-2])
            last = int(parts_bulk[-1])
        except Exception:
            bot.send_message(message.chat.id, "❌ رابط إرسال المجموعة غير صحيح.")
            return

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT file_id, episode_name, series_name
            FROM episodes
            WHERE series_id = ? OR series_name LIKE ?
            ORDER BY season ASC, episode ASC, id ASC
            """,
            (sid, f"%{sid}%")
        )
        db_rows = cursor.fetchall()
        conn.close()

        if not db_rows:
            bot.send_message(message.chat.id, "❌ لم يتم العثور على حلقات لهذا المسلسل.")
            return

        series_name = db_rows[0][2]
        selected = db_rows[first - 1:last]

        if not selected:
            bot.send_message(message.chat.id, "❌ المجموعة المطلوبة غير متوفرة.")
            return

        bot.send_message(
            message.chat.id,
            f"📥 جاري إرسال الحلقات ({first} إلى {last}) من مسلسل *{safe_markdown(series_name)}*...",
            parse_mode="Markdown"
        )

        sent = 0
        for file_id, episode_name, _ in selected:
            try:
                bot.send_video(
                    message.chat.id,
                    file_id,
                    caption=episode_name,
                    parse_mode="Markdown",
                    protect_content=is_blocked
                )
                sent += 1
                time.sleep(1)
            except Exception as e:
                print(f"BULK SEND ERROR: {e}")

        bot.send_message(message.chat.id, f"✅ تم إرسال {sent} حلقة بنجاح.")
        return

    # حلقة واحدة
    if raw.startswith("episode_"):
        episode_id = raw.replace("episode_", "")
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT file_id, episode_name FROM episodes WHERE id=?", (episode_id,))
        episode = cursor.fetchone()
        conn.close()

        if episode:
            file_id, episode_name = episode
            bot.send_video(message.chat.id, file_id, caption=episode_name, parse_mode="Markdown", protect_content=is_blocked)
        else:
            bot.send_message(message.chat.id, "❌ الحلقة غير موجودة أو تم حذفها.")
        return

    # مسلسل كامل
    if raw.startswith("series_"):
        link_id = raw.replace("series_", "")
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT series_name, series_id FROM links WHERE link_id=?", (link_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            bot.send_message(message.chat.id, "❌ اللينك غير صالح")
            return

        series_name, series_id = row
        cursor.execute(
            """
            SELECT file_id, episode_name
            FROM episodes
            WHERE series_id = ? OR series_name LIKE ?
            ORDER BY season ASC, episode ASC, id ASC
            """,
            (series_id, f"%{series_name}%")
        )
        episodes = cursor.fetchall()
        conn.close()

        if not episodes:
            bot.send_message(message.chat.id, "❌ لا توجد حلقات لهذا المسلسل")
            return

        series_sessions[message.chat.id] = {"episodes": episodes, "index": 0, "blocked": is_blocked}
        bot.send_message(message.chat.id, f"🎬 *{series_name}*\n📂 عدد الحلقات: {len(episodes)}", parse_mode="Markdown")
        send_next_batch(message.chat.id, batch_size=10, protect=is_blocked)
        return


def send_next_batch(chat_id, batch_size=10, protect=False, send_all=False):
    session = series_sessions.get(chat_id)
    if not session:
        return

    episodes = session["episodes"]
    index = session["index"]
    end = len(episodes) if send_all else index + batch_size
    batch = episodes[index:end]

    for file_id, episode_name in batch:
        bot.send_video(chat_id, file_id, caption=episode_name, parse_mode="Markdown", protect_content=protect)
        time.sleep(1)

    session["index"] = end
    if end < len(episodes):
        remaining = len(episodes) - end
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("📥 عايز 10 حلقات كمان", callback_data="send_more_10"),
            InlineKeyboardButton(f"📦 ابعت باقي المسلسل ({remaining})", callback_data="send_all")
        )
        bot.send_message(chat_id, f"⬇️ لسه فاضل {remaining} حلقة", reply_markup=markup)
    else:
        bot.send_message(chat_id, "✅ تم إرسال جميع الحلقات")
        series_sessions.pop(chat_id, None)


@bot.callback_query_handler(func=lambda call: call.data == "send_more_10")
def send_more_10_handler(call):
    bot.answer_callback_query(call.id)
    send_next_batch(call.message.chat.id, batch_size=10)


@bot.callback_query_handler(func=lambda call: call.data == "send_all")
def send_all_handler(call):
    bot.answer_callback_query(call.id)
    send_next_batch(call.message.chat.id, send_all=True)


# =========================================================
# 📥 استلام اسم المسلسل للدفعات من الأدمن
# =========================================================

@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID and message.chat.type == "private" and WAITING_FOR_BATCH_NAME
)
def receive_batch_series_name(message):
    global WAITING_FOR_BATCH_NAME
    series_name = message.text.strip()

    if not series_name:
        bot.reply_to(message, "❌ اكتب اسم المسلسل")
        return

    with BATCH_LOCK:
        videos = BATCH_VIDEOS.copy()
        BATCH_VIDEOS.clear()
        WAITING_FOR_BATCH_NAME = False

    if not videos:
        bot.reply_to(message, "❌ الدفعة فاضية")
        return

    numeric_videos = all(item.get("number") is not None for item in videos)
    if numeric_videos:
        videos.sort(key=lambda x: x["number"])
    else:
        videos.sort(key=lambda x: (x["season_episode"][0], x["season_episode"][1]) if x.get("season_episode") else (999, 999))

    series_id = get_or_create_series_id(series_name, "series")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT link_id FROM links WHERE series_name=? OR series_id=?", (series_name, series_id))
    link_row = cursor.fetchone()
    link_id = link_row[0] if link_row else None

    saved_count = 0
    qualities = set()
    saved_episodes = []

    for item in videos:
        file_id = item["file_id"]
        quality = normalize_quality(item.get("quality") or "HD")
        number = item.get("number")
        season_episode = item.get("season_episode")

        cursor.execute("SELECT id FROM episodes WHERE file_id=?", (file_id,))
        if cursor.fetchone():
            continue

        if season_episode:
            season, episode = season_episode
            final_title = f"{series_name} S{season:02d} E{episode:02d} - {quality}"
            notification_episode = f"S{season:02d} E{episode:02d}"
            ep_season = season
            ep_num = episode
        elif number is not None:
            final_title = f"{series_name} حلقة {number} - {quality}"
            notification_episode = number
            ep_season = 1
            ep_num = number
        else:
            final_title = f"{series_name} - {quality}"
            notification_episode = None
            ep_season = 1
            ep_num = 0

        saved_episodes.append(final_title)
        linked_caption = f"[{final_title}](https://t.me/cimabotbest)"

        cursor.execute(
            """
            INSERT INTO episodes
            (series_id, series_name, episode_name, file_id, quality, media_type, season, episode, release_year, views, added_date, link_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                series_id,
                series_name,
                linked_caption,
                file_id,
                quality,
                "series",
                ep_season,
                ep_num,
                "",
                0,
                datetime.now().isoformat(),
                link_id
            )
        )
        ep_id = cursor.lastrowid
        saved_count += 1
        qualities.add(quality)

        if notification_episode:
            try:
                send_new_episode_notification(series_name, notification_episode, quality, ep_id)
            except Exception as e:
                print("NOTIFY ERROR:", e)

    conn.commit()
    conn.close()

    SERIES_CACHE.clear()
    FAST_SEARCH_CACHE.clear()

    eps_text = "\n".join(saved_episodes[:30])
    qualities_text = " | ".join(sorted(qualities))
    bot.send_message(
        ADMIN_ID,
        f"✅ تم تسجيل جميع الفيديوهات\n\n🎬 {series_name}\n\n📺 الحلقات:\n{eps_text}\n\n🎞️ الجودات: {qualities_text}\n\n🔥 العدد: {saved_count}"
    )


# =========================================================
# 💬 معالجة الرسائل الخاصة (الميديا، الروابط، والدعم الفني)
# =========================================================

@bot.message_handler(
    func=lambda message: message.chat.type == "private" and message.from_user.id != ADMIN_ID,
    content_types=['video', 'photo', 'document']
)
def handle_user_media(message):
    user = message.from_user
    user_id = user.id
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎯 رد عليه", callback_data=f"reply_{user_id}"))

    if message.video:
        bot.send_video(ADMIN_ID, message.video.file_id, caption=f"🎥 فيديو من {user.first_name}\n🆔 `{user_id}`", reply_markup=markup, parse_mode="Markdown")
    elif message.photo:
        bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"🖼 صورة من {user.first_name}\n🆔 `{user_id}`", reply_markup=markup, parse_mode="Markdown")
    elif message.document:
        bot.send_document(ADMIN_ID, message.document.file_id, caption=f"📎 ملف من {user.first_name}\n🆔 `{user_id}`", reply_markup=markup, parse_mode="Markdown")


# =========================================================
# 🤖 الشات بالذكاء الاصطناعي وروابط التحميل (VIP & AI)
# =========================================================

def ai_show_movie(chat_id, title, reply_to=None):
    class FakeUser:
        id = 0
        first_name = "سهرة"

    class FakeChat:
        type = "private"
        id = chat_id

    class FakeMessage:
        text = title
        chat = FakeChat()
        from_user = FakeUser()
        message_id = reply_to or 0

    private_search_mode[0] = True
    show_movies(FakeMessage())


@bot.message_handler(func=lambda message: message.chat.type == "private" and not message.text.startswith('/'), content_types=['text'])
def private_user_text_dispatcher(message):
    user_id = message.from_user.id
    user = message.from_user
    user_text = message.text.strip()
    username = f"@{user.username}" if user.username else "بدون يوزر"

    # فحص هل المستخدم VIP
    is_vip = False
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        cursor.execute("SELECT end_date FROM subscriptions WHERE user_id=?", (user_id,))
        row = cursor.fetchone()
        conn.commit()
        conn.close()

        if row:
            end_date = datetime.fromisoformat(row[0])
            if datetime.now() <= end_date:
                is_vip = True
    except Exception as e:
        print("DB VIP CHECK ERROR:", e)

    # 1. لو الرسالة تحتوي على رابط فيديو للتحميل
    if "http://" in user_text or "https://" in user_text:
        if not is_vip:
            bot.send_message(
                message.chat.id,
                "عذراً يا بطل! 🌟 ميزة التحميل المباشر من الروابط متاحة فقط لمشتركي VIP.\n\nتواصل مع المطور للاشتراك! 👑✨",
                reply_to_message_id=message.message_id
            )
            bot.send_message(ADMIN_ID, f"🚫 محاولة تحميل من غير مشترك:\nالاسم: {user.first_name}\nID: `{user_id}`")
            return

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🎯 رد عليه", callback_data=f"reply_{user_id}"))
        admin_info = (
            f"🌟 **طلب تحميل جديد (VIP)**\n\n"
            f"👤 الاسم: {user.first_name}\n"
            f"🆔 الآيدي: `{user_id}`\n"
            f"🏷 اليوزر: {username}\n"
            f"🌐 الرابط: {user_text}"
        )
        bot.send_message(ADMIN_ID, admin_info, parse_mode="Markdown", reply_markup=markup)
        t = threading.Thread(target=process_video, args=(message,))
        t.start()
        return

    # 2. لو المستخدم أدمن
    if user_id == ADMIN_ID:
        return

    # 3. لو المستخدم ليس مشتركاً، يتم تحويل رسالته كدعم فني للأدمن
    if not is_vip:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🎯 رد عليه", callback_data=f"reply_{user_id}"))
        bot.send_message(
            ADMIN_ID,
            f"📩 **رسالة من مستخدم:** {user.first_name}\n🆔 الآيدي: `{user_id}`\n🏷 اليوزر: {username}\n\n{user_text}",
            parse_mode="Markdown",
            reply_markup=markup
        )
        bot.reply_to(
            message,
            "عذراً يا بطل 🌟\nميزة الذكاء الاصطناعي والترشيحات متاحة لمشتركي VIP فقط 👑\nتم تحويل رسالتك للدعم الفني وسيقوم المطور بالرد عليك قريباً."
        )
        return

    # 4. للمشتركين VIP -> تشغيل نظام الذكاء الاصطناعي "سهرة"
    if user_id in search_sessions or private_search_mode.get(user_id):
        return

    try:
        bot.send_chat_action(message.chat.id, 'typing')
    except Exception:
        pass

    try:
        current_date = datetime.now().strftime("%Y-%m-%d")
        full_prompt = f"""
التاريخ الحالي: {current_date}

اسمك: سهرة 🎬

شخصيتك:
- ولد مصري روش وخفيف الدم.
- خبير أفلام ومسلسلات.
- بتتكلم بالعامية المصرية.
- ردودك قصيرة وطبيعية.

مهم جداً:

1- لو المستخدم بيسأل على فيلم أو مسلسل موجود بعينه:
SEARCH: اسم العمل الرسمي فقط

2- لو المستخدم طالب ترشيحات:
ارجع JSON فقط:
{{
  "titles": ["title1", "title2", "title3", "title4", "title5"]
}}

3- لو دردشة عادية أو سؤال عام، رد بشكل طبيعي وودود.

رسالة المستخدم:
{user_text}
"""
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt
        )

        if not response or not response.text:
            bot.reply_to(message, "معلش يا صاحبي دماغي هنجت شوية 🤯")
            return

        reply = response.text.strip()

        if reply.startswith("SEARCH:"):
            title = reply.replace("SEARCH:", "").strip()
            try:
                ai_show_movie(chat_id=message.chat.id, title=title, reply_to=message.message_id)
            except Exception as e:
                print("AI SEARCH ERROR:", e)
                bot.reply_to(message, "مش لاقي المطلوب للأسف 🥺")
            return

        try:
            data = json.loads(reply)
            titles = data.get("titles", [])
        except Exception:
            titles = []

        if titles:
            bot.send_message(message.chat.id, "يتم تجهيز الترشيحات، شوية صبر وهتكون عندك ❤️!")
            for title in titles:
                try:
                    ai_show_movie(chat_id=message.chat.id, title=title, reply_to=message.message_id)
                except Exception as e:
                    print("AI MOVIE ERROR:", e)
            return

        bot.reply_to(message, reply)

    except Exception as e:
        print("AI ERROR:", e)
        bot.send_message(
            message.chat.id,
            "استنى عليا بس يا نجم 😅🔥\nفي ضغط شوية دلوقتي.. تعالى كمان شوية وهنروق الدنيا سوا 💪"
        )


# =========================================================
# 🌐 Flask Server للـ Health Check على الاستضافة
# =========================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "OK", 200

def run_server():
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)


# =========================================================
# 🚀 تشغيل البوت والخدمات الخلفية
# =========================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 BOT STARTING...")
    print("=" * 60)

    try:
        health_thread = threading.Thread(target=run_server, daemon=True, name="HealthServerThread")
        health_thread.start()
        print("✅ Health server thread started")
    except Exception as e:
        print("❌ HEALTH SERVER ERROR:", repr(e))

    try:
        backup_thread = threading.Thread(
            target=start_auto_backup,
            args=(
                bot,
                DB_NAME,
                backup_conn,
                get_uptime,
                lambda: get_total_users(DB_NAME),
                lambda: get_total_content(DB_NAME),
                lambda: get_total_links(DB_NAME)
            ),
            daemon=True,
            name="AutoBackupThread"
        )
        backup_thread.start()
        print("✅ Automatic backup thread started")
    except Exception as e:
        print("❌ AUTO BACKUP THREAD ERROR:", repr(e))

    try:
        recommendation_thread = threading.Thread(target=recommendation_loop, daemon=True, name="RecommendationThread")
        recommendation_thread.start()
        print("✅ Recommendation thread started")
    except Exception as e:
        print("❌ RECOMMENDATION THREAD ERROR:", repr(e))

    try:
        expiry_thread = threading.Thread(target=expiry_loop, daemon=True, name="ExpiryThread")
        expiry_thread.start()
        print("✅ Subscription expiry check thread started")
    except Exception as e:
        print("❌ EXPIRY THREAD ERROR:", repr(e))

    try:
        bot.remove_webhook()
        print("✅ Webhook removed")
    except Exception as e:
        print("❌ WEBHOOK ERROR:", repr(e))

    print("📡 TELEGRAM POLLING RUNNING...")
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print("❌ TELEGRAM POLLING CRASH:", repr(e))
            time.sleep(15)
