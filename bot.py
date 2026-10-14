# -*- coding: utf-8 -*-
"""
Разговоры по душам — анонимная поддержка + анкеты + модерация
"""

import os
import re
import time
import sqlite3
import threading

import telebot
from telebot import types


# ══════════════════════════════════════════════════════
# КОНФИГ
# ══════════════════════════════════════════════════════
class Config:
    TOKEN = os.environ.get(
        "BOT_TOKEN",
        "8975520882:AAHSCwym6c8p6v1XZDIvtIyR2-y7se_niGU"
    )
    DEVELOPER_ID = 963549015
    SUPPORT_GROUP = -1004249566422
    ANKETA_GROUP = -1004460147391
    TECH_GROUP = -5528257493
    DB_PATH = "/tmp/secretary.db"

    RULES_URL = "https://telegra.ph/Pravila-dlya-polzovatelej-tesnyj-angel-07-24"

    FLOOD_INTERVAL = 2
    MUTE_TIME = 30
    ANKETA_COOLDOWN = 5 * 3600

    MIN_SETROLE = 5
    MIN_REMOVEROLE = 5
    MIN_BAN = 5
    MIN_UNBAN = 5
    MIN_WARN = 5
    MIN_UNWARN = 5
    MIN_KICK = 5
    MIN_MUTE = 5
    MIN_UNMUTE = 5
    MIN_BOTSTATS = 8
    MIN_LOGS = 8
    MIN_BROADCAST = 8
    MIN_SETPERM = 8
    MIN_CHECK = 1


RANKS = {
    0:   "Пользователь",
    1:   "Администратор",
    2:   "Младший администратор",
    3:   "Администратор бота",
    4:   "Старший администратор",
    5:   "Заместитель совладельца",
    6:   "Заместитель владельца",
    7:   "Совладелец",
    8:   "Владелец",
    100: "Разработчик",
}


# ══════════════════════════════════════════════════════
# ВОПРОСЫ АНКЕТ
# ══════════════════════════════════════════════════════
ANKETA_OBSHENIE = [
    "Ваш юз.", "Псевдоним/тег (Реальное имя запрещено).",
    "Возраст (Берём с 14 лет).", "Часовой пояс от мск.", "Ваш пол.",
    "Как вы думаете, сможете ли вы поддержать беседу на отвлечённые темы, если пользователь молчит и отвечает односложно?",
    "Умеете ли вы шутить и разряжать обстановку, не переходя в пошлость или чёрный юмор?",
    "Оценка вашей грамотности от 1 до 10.", "Готовы ли вы общаться на любые БЫТОВЫЕ темы?",
    "Воспринимаете ли вы людей и ситуации серьезно?", "Готовы ли вы проявлять уважение к администрации?",
    "Готовы ли вы выполнять норму 100 сообщений в неделю?", "Возникают ли трудности при общении с незнакомыми?",
    "Готовы ли вы соблюдать конфиденциальность?", "Сможете ли отвлечь человека от грустных мыслей?",
    "Как вы относитесь к флирту от пользователя?", "Что важнее: совет или весело провести время?",
    "Придумайте 10 тем для холодного собеседника.", "Пользователь написал пошлую шутку — ваш ответ?",
    "Вы нарушили правило, никто не заметил — действия?",
]

ANKETA_PODDERZHKA = [
    "Псевдоним/тег (Реальное имя запрещено).", "Возраст (с 14 лет).", "Часовой пояс от мск.", "Ваш пол.",
    "Есть ли опыт в проектах поддержки?", "Знаете ли что такое активное слушание, валидация?",
    "Оценка стрессоустойчивости от 1 до 10.", "Оценка грамотности от 1 до 10.",
    "Сохраняете ли спокойствие при агрессии?", "Воспринимаете ли людей серьёзно?",
    "Уважение к администрации?", "Норма 100 сообщений в неделю?", "Трудности с людьми в истерике?",
    "Конфиденциальность?", "Знаете запрещённые вопросы в кризисе?",
    "Что делать, если человек взял нож/таблетки?",
    "Слова поддержки на сообщение о 3-дневной апатии.",
    "Слова на сообщение про месть и интимные фото.",
    "Пользователь режет руку, мама позор семьи — действия?",
]

ANKETA_MONTAZH = [
    "Ваш юз.", "Псевдоним/тег.", "Возраст.", "Часовой пояс от МСК.",
    "Сколько часов в неделю готовы уделять монтажу?",
    "Готовы ли выполнять правки?", "Какие программы используете?",
    "Готовы ли работать с сырым материалом?", "Есть ли опыт создания видео?",
    "Опыт работы со звуком от 1 до 10?", "Трудности с большими текстами?",
    "3 идеи для 30-сек видео.", "Создайте 3 коротких видео до 30 сек.",
]

ANKETA_TYPES = {
    "obchenie":   ("ОБЩЕНИЕ",   ANKETA_OBSHENIE),
    "podderzhka": ("ПОДДЕРЖКА", ANKETA_PODDERZHKA),
    "montazh":    ("МОНТАЖ",    ANKETA_MONTAZH),
}


# ══════════════════════════════════════════════════════
# БАЗА
# ══════════════════════════════════════════════════════
class Storage:
    def __init__(self, path):
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        with self.lock:
            c = self.conn.cursor()
            c.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    pseudo TEXT UNIQUE,
                    nickname TEXT,
                    age TEXT,
                    need TEXT,
                    rank INTEGER DEFAULT 0,
                    agreement INTEGER DEFAULT 0,
                    banned INTEGER DEFAULT 0,
                    ban_reason TEXT,
                    warns INTEGER DEFAULT 0,
                    muted_until REAL DEFAULT 0,
                    last_msg REAL DEFAULT 0,
                    messages INTEGER DEFAULT 0,
                    joined TEXT
                );
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    admin_id INTEGER,
                    category TEXT,
                    status TEXT DEFAULT 'open',
                    created TEXT
                );
                CREATE TABLE IF NOT EXISTS tech_tickets (
                    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    admin_id INTEGER,
                    status TEXT DEFAULT 'open',
                    created TEXT
                );
                CREATE TABLE IF NOT EXISTS anketa_subs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    anketa_type TEXT,
                    status TEXT DEFAULT 'pending',
                    created REAL,
                    answers TEXT,
                    msg_id INTEGER
                );
                CREATE TABLE IF NOT EXISTS replies (
                    admin_msg_id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    ticket_id INTEGER
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT,
                    admin_id INTEGER,
                    target_id INTEGER,
                    details TEXT,
                    date TEXT
                );
                CREATE TABLE IF NOT EXISTS command_perms (
                    command TEXT PRIMARY KEY,
                    min_rank INTEGER
                );
            """)
            c.execute("INSERT OR IGNORE INTO settings VALUES('agreement', 'Прежде чем продолжить, ознакомься с правилами использования бота.')")
            c.execute("INSERT OR IGNORE INTO users(user_id, rank, nickname, joined) VALUES(?, 100, 'Разработчик', ?)",
                      (Config.DEVELOPER_ID, time.strftime("%d.%m.%Y")))

            defaults = {
                "setrole": 5, "removerole": 5, "ban": 5, "unban": 5,
                "warn": 5, "unwarn": 5, "kick": 5, "mute": 5, "unmute": 5,
                "check": 1, "botstats": 8, "logs": 8, "broadcast": 8,
            }
            for cmd, rank in defaults.items():
                c.execute("INSERT OR IGNORE INTO command_perms VALUES(?, ?)", (cmd, rank))
            self.conn.commit()

    def _exec(self, sql, params=(), fetch=None):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(sql, params)
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
            self.conn.commit()
            return cur.lastrowid

    def get_user(self, uid):
        row = self._exec("SELECT * FROM users WHERE user_id=?", (uid,), "one")
        if not row:
            self._exec("INSERT INTO users(user_id, joined) VALUES(?, ?)",
                       (uid, time.strftime("%d.%m.%Y")))
            row = self._exec("SELECT * FROM users WHERE user_id=?", (uid,), "one")
        return row

    def set_user(self, uid, **kwargs):
        if not kwargs:
            return
        fields = ", ".join(f"{k}=?" for k in kwargs)
        self._exec(f"UPDATE users SET {fields} WHERE user_id=?",
                   list(kwargs.values()) + [uid])

    def set_rank(self, uid, rank, nickname=None):
        self._exec("UPDATE users SET rank=?, nickname=? WHERE user_id=?",
                   (int(rank), nickname, uid))

    def remove_role(self, uid):
        self._exec("UPDATE users SET rank=0, nickname=NULL WHERE user_id=?", (uid,))

    def pseudo_taken(self, pseudo):
        return self._exec("SELECT user_id FROM users WHERE pseudo=?", (pseudo,), "one") is not None

    def get_ban(self, uid):
        row = self._exec("SELECT * FROM users WHERE user_id=?", (uid,), "one")
        if row and row["banned"]:
            return row
        return None

    def set_ban(self, uid, banned, reason=""):
        self._exec("UPDATE users SET banned=?, ban_reason=? WHERE user_id=?",
                   (banned, reason, uid))

    def set_warns(self, uid, count):
        self._exec("UPDATE users SET warns=? WHERE user_id=?", (count, uid))

    def create_ticket(self, uid, category):
        return self._exec(
            "INSERT INTO tickets(user_id, category, created) VALUES(?, ?, ?)",
            (uid, category, time.strftime("%d.%m.%Y %H:%M")))

    def get_open_ticket(self, uid):
        return self._exec(
            "SELECT * FROM tickets WHERE user_id=? AND status='open' ORDER BY ticket_id DESC LIMIT 1",
            (uid,), "one")

    def get_ticket(self, tid):
        return self._exec("SELECT * FROM tickets WHERE ticket_id=?", (tid,), "one")

    def set_ticket_admin(self, tid, admin_id):
        self._exec("UPDATE tickets SET admin_id=? WHERE ticket_id=?", (admin_id, tid))

    def close_ticket(self, tid):
        self._exec("UPDATE tickets SET status='closed' WHERE ticket_id=?", (tid,))

    def create_tech_ticket(self, uid):
        return self._exec(
            "INSERT INTO tech_tickets(user_id, created) VALUES(?, ?)",
            (uid, time.strftime("%d.%m.%Y %H:%M")))

    def get_open_tech_ticket(self, uid):
        return self._exec(
            "SELECT * FROM tech_tickets WHERE user_id=? AND status='open' ORDER BY ticket_id DESC LIMIT 1",
            (uid,), "one")

    def close_tech_ticket(self, tid):
        self._exec("UPDATE tech_tickets SET status='closed' WHERE ticket_id=?", (tid,))

    def has_pending_anketa(self, uid):
        return self._exec("SELECT id FROM anketa_subs WHERE user_id=? AND status='pending'",
                          (uid,), "one") is not None

    def last_anketa_time(self, uid):
        row = self._exec(
            "SELECT created FROM anketa_subs WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (uid,), "one")
        return float(row["created"]) if row else 0

    def create_anketa(self, uid, anketa_type, answers):
        return self._exec(
            "INSERT INTO anketa_subs(user_id, anketa_type, answers, created) VALUES(?, ?, ?, ?)",
            (uid, anketa_type, "\n---\n".join(answers), time.time()))

    def set_anketa_status(self, aid, status):
        self._exec("UPDATE anketa_subs SET status=? WHERE id=?", (status, aid))

    def get_anketa(self, aid):
        return self._exec("SELECT * FROM anketa_subs WHERE id=?", (aid,), "one")

    def save_reply(self, msg_id, uid, tid):
        self._exec("REPLACE INTO replies VALUES(?, ?, ?)", (msg_id, uid, tid))

    def get_reply(self, msg_id):
        return self._exec("SELECT * FROM replies WHERE admin_msg_id=?", (msg_id,), "one")

    def get_setting(self, key, default=""):
        row = self._exec("SELECT value FROM settings WHERE key=?", (key,), "one")
        return row["value"] if row else default

    def add_log(self, action, admin_id=None, target_id=None, details=""):
        self._exec(
            "INSERT INTO logs(action, admin_id, target_id, details, date) VALUES(?, ?, ?, ?, ?)",
            (action, admin_id, target_id, details, time.strftime("%d.%m.%Y %H:%M:%S")))

    def get_logs(self, limit=10):
        return self._exec("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,), "all") or []

    def get_all_users(self):
        return self._exec("SELECT user_id FROM users", fetch="all") or []

    def get_stats(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) as cnt FROM users")
            total = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM users WHERE rank >= 1")
            admins = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM users WHERE rank = 0")
            users_only = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM users WHERE banned=1")
            banned = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM users WHERE messages > 0")
            active = cur.fetchone()["cnt"]
            cur.execute("SELECT SUM(messages) as s FROM users")
            total_messages = cur.fetchone()["s"] or 0
            cur.execute("SELECT SUM(warns) as s FROM users")
            total_warns = cur.fetchone()["s"] or 0
        return {
            "total": total, "admins": admins, "users_only": users_only,
            "banned": banned, "active": active,
            "total_messages": total_messages, "total_warns": total_warns,
        }

    def get_perm(self, command, default=8):
        row = self._exec("SELECT min_rank FROM command_perms WHERE command=?",
                         (command,), "one")
        return row["min_rank"] if row else default


db = Storage(Config.DB_PATH)
bot = telebot.TeleBot(Config.TOKEN, parse_mode="HTML")

try:
    bot.remove_webhook(drop_pending_updates=True)
    print("✅ Webhook удалён")
except Exception as e:
    print(f"⚠️ Webhook: {e}")

talk_sessions = {}
anketa_sessions = {}


# ══════════════════════════════════════════════════════
# ХЕЛПЕРЫ
# ══════════════════════════════════════════════════════
def rank_of(uid):
    if uid == Config.DEVELOPER_ID:
        return 100
    return db.get_user(uid)["rank"]


def rank_label(r):
    if r == 100:
        return "⚙️ Разработчик"
    if r == 0:
        return "👤 Пользователь"
    return f"🛡 {RANKS.get(r, 'Неизвестно')}"


def nick_tg(uid):
    try:
        u = bot.get_chat(uid)
        return u.first_name or f"ID{uid}"
    except Exception:
        return f"ID{uid}"


def safe_username(uid):
    u = db.get_user(uid)
    if u["username"]:
        return f"@{u['username']}"
    try:
        c = bot.get_chat(uid)
        return f"@{c.username}" if c.username else "без username"
    except Exception:
        return "без username"


def admin_pseudo(uid):
    nick = db.get_user(uid)["nickname"]
    return f"(#{nick})" if nick else "(#Администратор)"


def is_flood(uid):
    u = db.get_user(uid)
    now = time.time()
    if u["muted_until"] and now < u["muted_until"]:
        return True
    if u["last_msg"] and now - u["last_msg"] < Config.FLOOD_INTERVAL:
        db.set_user(uid, muted_until=now + Config.MUTE_TIME)
        return True
    db.set_user(uid, last_msg=now)
    return False


def check_access(message, min_rank):
    if rank_of(message.from_user.id) < min_rank:
        bot.reply_to(message, "❌ Недостаточно прав!")
        return False
    return True


def parse_pseudo(raw):
    if not raw:
        return None, "Введите псевдоним через \"#\" пример: #бес"
    raw = raw.strip()
    if not raw.startswith("#"):
        return None, "Введите псевдоним через \"#\" пример: #бес"
    name = raw[1:]
    if not name:
        return None, "Введите псевдоним через \"#\" пример: #бес"
    if re.search(r"\d", name):
        return None, "Используйте только буквы пример: #бес"
    if not re.match(r"^[A-Za-zА-Яа-яЁё]+$", name):
        return None, "Используйте только буквы пример: #бес"
    pseudo = "#" + name
    if db.pseudo_taken(pseudo):
        return None, "Этот псевдоним уже занят!"
    return pseudo, None


def resolve_user(message, text):
    if message.reply_to_message:
        rt = message.reply_to_message
        if rt.from_user.id == bot.get_me().id:
            r = db.get_reply(rt.message_id)
            if r:
                return r["user_id"]
        return rt.from_user.id
    if not text:
        return None
    arg = text.strip().split()[0]
    if arg.isdigit():
        return int(arg)
    if arg.startswith("@"):
        try:
            return bot.get_chat(arg).id
        except Exception:
            return None
    return None


def main_menu_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        types.KeyboardButton("💬 Поговорить с бесом"),
        types.KeyboardButton("🧑‍💻 Тех поддержка"),
        types.KeyboardButton("🖤 Стать бесом"),
    )
    return kb


def dialog_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        types.KeyboardButton("❌ Разорвать связь"),
        types.KeyboardButton("⭐ Поставить оценку"),
        types.KeyboardButton("🔄 Сменить беса"),
        types.KeyboardButton("👑 Позвать беса"),
    )
    return kb


def need_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("💙 Поддержка", callback_data="need_Поддержка"),
        types.InlineKeyboardButton("💬 Общение", callback_data="need_Общение"),
        types.InlineKeyboardButton("🎯 Универсал", callback_data="need_Универсал"),
    )
    return kb


def anketa_types_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("💬 Анкета на общение", callback_data="ank_obchenie"),
        types.InlineKeyboardButton("💙 Анкета на поддержку", callback_data="ank_podderzhka"),
        types.InlineKeyboardButton("🎬 Анкета на монтажёра", callback_data="ank_montazh"),
    )
    return kb


def rating_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    for i in range(1, 6):
        kb.add(types.InlineKeyboardButton(str(i), callback_data=f"rate_{i}"))
    return kb


def anketa_review_kb(aid):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ Одобрено", callback_data=f"ank_ok_{aid}"),
        types.InlineKeyboardButton("❌ Отказано", callback_data=f"ank_no_{aid}"),
    )
    return kb


# ══════════════════════════════════════════════════════
# /start
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["start"])
def cmd_start(message):
    if message.chat.type != "private":
        return
    uid = message.from_user.id
    u = db.get_user(uid)

    if not u["agreement"]:
        agreement = db.get_setting("agreement",
            "Прежде чем продолжить, ознакомься с правилами использования бота.")
        text = (
            "❗<b>Пользовательское соглашение</b>\n\n"
            f"{agreement}\n\n"
            "Нажми на кнопку <b>«Принять соглашение»</b>, чтобы продолжить."
        )
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton("✅ Принять соглашение", callback_data="accept"),
            types.InlineKeyboardButton("📜 Пользовательское соглашение", url=Config.RULES_URL),
        )
        return bot.send_message(uid, text, reply_markup=kb)

    send_welcome(uid)


def send_welcome(uid):
    text = (
        "Соглашение принято ✅\n\n"
        "🌙 <b>ᴨᴩиʙᴇт, зᴀбᴧудиʙɯᴀя душᴀ</b> 🖤\n\n"
        "За этим экраном — не роботы, а живые люди. Мы здесь, "
        "чтобы выслушать тебя и поговорить по душам.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🕯️ <b>ᴄообщᴇния доходят нᴇ ᴄᴩᴀзу</b>\n\n"
        "Пожалуйста, не блокируй бот, если тебе не ответили в первые "
        "10–20 минут.\n\n"
        "🖤 <b>ᴋᴀᴋ нᴀчᴀᴛь?</b>\n\n"
        "▸ Поговорить с бесом\n▸ Тех поддержка\n▸ Стать бесом"
    )
    bot.send_message(uid, text, reply_markup=main_menu_kb())


@bot.callback_query_handler(func=lambda c: c.data == "accept")
def cb_accept(call):
    uid = call.from_user.id
    db.set_user(uid, agreement=1)
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    send_welcome(uid)
    bot.answer_callback_query(call.id, "✅ Соглашение принято")


# ══════════════════════════════════════════════════════
# ПОГОВОРИТЬ С БЕСОМ
# ══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "💬 Поговорить с бесом")
def btn_talk(message):
    uid = message.from_user.id
    if db.get_open_ticket(uid):
        return bot.send_message(uid, "⚠️ У вас уже есть активный запрос!")
    talk_sessions[uid] = {"step": 0, "pseudo": None, "age": None}
    bot.send_message(uid,
        "💭 <b>Скрыть истинное имя (Псевдоним)</b>\n\n"
        "Придумай псевдоним — только буквы, через #. Пример: <code>#бес</code>")


@bot.message_handler(func=lambda m: m.chat.type == "private" and m.from_user.id in talk_sessions,
                     content_types=["text"])
def talk_step(message):
    uid = message.from_user.id
    state = talk_sessions[uid]
    text = (message.text or "").strip()

    if state["step"] == 0:
        pseudo, err = parse_pseudo(text)
        if err:
            return bot.send_message(uid, err)
        state["pseudo"] = pseudo
        state["step"] = 1
        return bot.send_message(uid, "🙂 Какого возраста хочешь себе беса?")

    if state["step"] == 1:
        if not text.isdigit():
            return bot.send_message(uid, "Используйте только цифры!")
        state["age"] = text
        state["step"] = 2
        return bot.send_message(uid, "💭 Что тебе нужно?", reply_markup=need_kb())


@bot.callback_query_handler(func=lambda c: c.data.startswith("need_"))
def cb_need(call):
    uid = call.from_user.id
    if uid not in talk_sessions:
        return bot.answer_callback_query(call.id, "Анкета не активна")
    need = call.data.split("_", 1)[1]
    state = talk_sessions.pop(uid)

    db.set_user(uid, pseudo=state["pseudo"], age=state["age"], need=need)
    tid = db.create_ticket(uid, need)

    bot.edit_message_text(
        "✔️ <b>Запрос отправлен!</b>\n\n"
        "❤️ Ожидай — кто-то из поддержки скоро напишет.\n\n"
        "<i>Можешь просто побыть здесь</i>",
        call.message.chat.id, call.message.message_id)

    post_new_ticket(uid, tid, need)
    bot.answer_callback_query(call.id, "✅ Запрос отправлен")


def post_new_ticket(uid, tid, need):
    u = db.get_user(uid)
    text = (
        f"🆕 <b>Новый запрос</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Псевдоним:</b> {u['pseudo']}\n"
        f"🎂 <b>Возраст:</b> {u['age']}\n"
        f"🎯 <b>Нужно:</b> {need}\n"
        f"🆔 <code>{uid}</code>\n"
        f"🎫 <b>Заявка:</b> #{tid}"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Взять", callback_data=f"take_{tid}"))
    try:
        sent = bot.send_message(Config.SUPPORT_GROUP, text, reply_markup=kb)
        db.save_reply(sent.message_id, uid, tid)
    except Exception as e:
        print(f"[post_new_ticket] {e}")


@bot.callback_query_handler(func=lambda c: c.data.startswith("take_"))
def cb_take(call):
    tid = int(call.data.split("_", 1)[1])
    admin_id = call.from_user.id
    t = db.get_ticket(tid)
    if not t or t["status"] != "open":
        return bot.answer_callback_query(call.id, "Заявка уже закрыта")
    if t["admin_id"]:
        return bot.answer_callback_query(call.id, "Заявку уже взяли", show_alert=True)

    db.set_ticket_admin(tid, admin_id)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(Config.SUPPORT_GROUP,
        f"🖤 <b>Заявка #{tid} принята</b>\n"
        f"👮 {call.from_user.first_name}")

    try:
        bot.send_message(t["user_id"],
            f"✔️ <b>Бес тут!</b>\n\n"
            f"❤️ Я здесь, чтобы выслушать и поддержать.\n\n"
            f"💭 Просто пиши — я всё вижу.",
            reply_markup=dialog_kb())
    except Exception:
        pass
    bot.answer_callback_query(call.id, "✅ Принято")


# ══════════════════════════════════════════════════════
# РАЗОРВАТЬ СВЯЗЬ
# ══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "❌ Разорвать связь")
def btn_close(message):
    uid = message.from_user.id
    t = db.get_open_ticket(uid)
    if not t:
        return bot.send_message(uid, "⚠️ Нет активного обращения.")
    db.close_ticket(t["ticket_id"])
    bot.send_message(uid,
        "✔️ <b>Обращение завершено.</b>\n\n"
        "⭐ Оцени, пожалуйста, работу поддержки:")
    bot.send_message(uid, "Выберите оценку:", reply_markup=rating_kb())


@bot.callback_query_handler(func=lambda c: c.data.startswith("rate_"))
def cb_rate(call):
    uid = call.from_user.id
    score = int(call.data.split("_", 1)[1])
    stars = "⭐" * score
    bot.edit_message_text(
        f"✔️ Оценка {stars} — спасибо!\n\n"
        "<i>Если понадобится — я здесь.</i>",
        call.message.chat.id, call.message.message_id)
    bot.send_message(uid, "Главное меню:", reply_markup=main_menu_kb())
    bot.answer_callback_query(call.id)


# ══════════════════════════════════════════════════════
# СМЕНИТЬ БЕСА
# ══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "🔄 Сменить беса")
def btn_change(message):
    uid = message.from_user.id
    t = db.get_open_ticket(uid)
    if not t:
        return bot.send_message(uid, "⚠️ Нет активного обращения.")
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("❌ Да, сменить", callback_data="change_yes"),
        types.InlineKeyboardButton("🔵 Отмена", callback_data="change_no"),
    )
    bot.send_message(uid,
        f"🔄 <b>Сменить беса?</b>\n\n"
        f"Текущий администратор будет уведомлён, и к тебе назначат другого.\n"
        f"Осталось смен сегодня: 3",
        reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "change_no")
def cb_change_no(call):
    bot.edit_message_text("✔️ Отмена — администратор остался прежним.",
                          call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data == "change_yes")
def cb_change_yes(call):
    uid = call.from_user.id
    t = db.get_open_ticket(uid)
    if not t:
        return bot.answer_callback_query(call.id, "Нет активного обращения")
    db._exec("UPDATE tickets SET admin_id=NULL WHERE ticket_id=?", (t["ticket_id"],))
    try:
        bot.send_message(Config.SUPPORT_GROUP,
            f"🔄 Заявка #{t['ticket_id']} — админ сменён пользователем.")
    except Exception:
        pass
    bot.edit_message_text(
        "Вы успешно сменили администратора, ожидайте когда вам напишет новый администратор",
        call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)


# ══════════════════════════════════════════════════════
# ПОЗВАТЬ БЕСА
# ══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "👑 Позвать беса")
def btn_call(message):
    uid = message.from_user.id
    t = db.get_open_ticket(uid)
    if not t:
        return bot.send_message(uid, "⚠️ Нет активного обращения.")
    try:
        bot.send_message(Config.SUPPORT_GROUP,
            f"👑 <b>Пользователь зовёт беса</b>\n"
            f"🎫 Заявка #{t['ticket_id']}\n"
            f"👤 {db.get_user(uid)['pseudo']}")
    except Exception:
        pass
    bot.send_message(uid, "✅ Бес получил знак и скоро вернётся.")


@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "⭐ Поставить оценку")
def btn_rating(message):
    uid = message.from_user.id
    t = db.get_open_ticket(uid)
    if not t:
        return bot.send_message(uid, "⚠️ Нет активного обращения.")
    bot.send_message(uid, "⭐ Выбери оценку:", reply_markup=rating_kb())


# ══════════════════════════════════════════════════════
# ТЕХ ПОДДЕРЖКА
# ══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "🧑‍💻 Тех поддержка")
def btn_tech(message):
    uid = message.from_user.id
    if db.get_open_tech_ticket(uid):
        return bot.send_message(uid, "⚠️ У вас уже есть активное обращение.")
    tid = db.create_tech_ticket(uid)
    bot.send_message(uid,
        f"✔️ <b>Обращение #{tid} принято!</b>\n\n"
        f"<i>Ответим как можно скорее.</i>\n"
        f"<i>Чтобы выйти из диалога, нажми</i> <b>«Разорвать связь»</b>.")
    try:
        sent = bot.send_message(Config.TECH_GROUP,
            f"🧑‍💻 <b>Тех.обращение #{tid}</b>\n"
            f"🆔 <code>{uid}</code>")
        db.save_reply(sent.message_id, uid, tid)
    except Exception as e:
        print(f"[tech] {e}")


# ══════════════════════════════════════════════════════
# СТАТЬ БЕСОМ (АНКЕТЫ)
# ══════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "🖤 Стать бесом")
def btn_become(message):
    uid = message.from_user.id
    if db.has_pending_anketa(uid):
        return bot.send_message(uid, "⚠️ Вы уже отправляете анкету!")

    last = db.last_anketa_time(uid)
    if last and time.time() - last < Config.ANKETA_COOLDOWN:
        left = int((Config.ANKETA_COOLDOWN - (time.time() - last)) // 3600)
        return bot.send_message(uid, f"⏳ Анкету можно писать раз в 5 часов. Осталось: {left}ч")

    bot.send_message(uid, "🖤 <b>Стать бесом</b>\n\nВыберите на кого хотите пойти:",
                     reply_markup=anketa_types_kb())


@bot.callback_query_handler(func=lambda c: c.data.startswith("ank_"))
def cb_anketa_type(call):
    uid = call.from_user.id
    key = call.data.split("_", 1)[1]
    if key not in ANKETA_TYPES:
        return bot.answer_callback_query(call.id, "Ошибка")
    if db.has_pending_anketa(uid):
        return bot.answer_callback_query(call.id, "Вы уже отправляете анкету!", show_alert=True)

    anketa_sessions[uid] = {"type": key, "step": 0, "answers": []}
    title, questions = ANKETA_TYPES[key]

    bot.edit_message_text(
        f"📝 <b>Анкета на «{title}»</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>1/{len(questions)}</b>\n\n"
        f"{questions[0]}",
        call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)


@bot.message_handler(func=lambda m: m.chat.type == "private" and m.from_user.id in anketa_sessions,
                     content_types=["text", "photo", "video", "document"])
def anketa_step(message):
    uid = message.from_user.id
    state = anketa_sessions[uid]
    title, questions = ANKETA_TYPES[state["type"]]

    if message.text:
        state["answers"].append(message.text)
    elif message.photo:
        state["answers"].append("[фото]")
    elif message.video:
        state["answers"].append("[видео]")
    elif message.document:
        state["answers"].append(f"[файл: {message.document.file_name}]")
    else:
        state["answers"].append("[медиа]")

    state["step"] += 1

    if state["step"] < len(questions):
        bot.send_message(uid,
            f"<b>{state['step']+1}/{len(questions)}</b>\n\n"
            f"{questions[state['step']]}")
    else:
        answers = state["answers"]
        anketa_type = state["type"]
        del anketa_sessions[uid]

        aid = db.create_anketa(uid, anketa_type, answers)
        post_anketa(uid, aid, anketa_type, questions, answers)
        bot.send_message(uid, "Ваша анкета отправлена на рассмотрение администрации")


def post_anketa(uid, aid, anketa_type, questions, answers):
    title, _ = ANKETA_TYPES[anketa_type]
    u = db.get_user(uid)

    text = (
        f"📝 <b>Новая анкета — {title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Пользователь:</b> {safe_username(uid)} ({nick_tg(uid)})\n"
        f"🆔 <code>{uid}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
    )
    for i, (q, a) in enumerate(zip(questions, answers), 1):
        text += f"<b>{i}. {q}</b>\n> {a}\n\n"
    text += f"━━━━━━━━━━━━━━━━━━\n🎫 <b>Анкета:</b> #{aid}"

    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    try:
        for chunk in chunks[:-1]:
            bot.send_message(Config.ANKETA_GROUP, chunk)
        bot.send_message(Config.ANKETA_GROUP, chunks[-1],
                         reply_markup=anketa_review_kb(aid))
    except Exception as e:
        print(f"[post_anketa] {e}")


@bot.callback_query_handler(func=lambda c: c.data.startswith("ank_ok_") or c.data.startswith("ank_no_"))
def cb_anketa_decide(call):
    action, aid = call.data.split("_")[1], int(call.data.split("_")[2])
    a = db.get_anketa(aid)
    if not a or a["status"] != "pending":
        return bot.answer_callback_query(call.id, "Уже обработано")
    uid = a["user_id"]

    if action == "ok":
        db.set_anketa_status(aid, "approved")
        try:
            bot.send_message(uid,
                "Ваша анкета была одобрена ✅\n"
                "<i>Ожидайте, с вами свяжутся</i>")
        except Exception:
            pass
        bot.send_message(Config.ANKETA_GROUP, f"✅ Анкета #{aid} одобрена.")
    else:
        db.set_anketa_status(aid, "rejected")
        try:
            bot.send_message(uid, "Ваша анкета была отказана.")
        except Exception:
            pass
        bot.send_message(Config.ANKETA_GROUP, f"❌ Анкета #{aid} отказана.")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    bot.answer_callback_query(call.id)


# ══════════════════════════════════════════════════════
# КОМАНДЫ
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["help"])
def cmd_help(message):
    uid = message.from_user.id
    r = rank_of(uid)
    text = "📖 <b>Команды</b>\n\n"
    text += "<b>👤 Для всех:</b>\n/start /help /stats /close /rules /info\n\n"
    if r >= 1:
        text += "<b>🛠 Ранг 1+:</b>\n/check (reply)\n\n"
    if r >= 5:
        text += "<b>🧑‍💼 Ранг 5+:</b>\n"
        text += "/setrole @user N #ник\n/removerole @user\n"
        text += "/ban /unban /warn /unwarn /kick /mute /unmute\n\n"
    if r >= 8:
        text += "<b>👑 Ранг 8+:</b>\n/broadcast /logs /botstats\n"
    bot.reply_to(message, text)


@bot.message_handler(commands=["stats"])
def cmd_stats(message):
    uid = message.from_user.id
    arg = message.text.partition(" ")[2].strip()

    if arg or message.reply_to_message:
        if rank_of(uid) < 1:
            return bot.reply_to(message, "❌ Недостаточно прав!")
        target = resolve_user(message, arg)
        if not target:
            return bot.reply_to(message, "❌ Пользователь не найден")
    else:
        target = uid

    u = db.get_user(target)
    text = (
        f"📊 <b>Профиль</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <code>{target}</code>\n"
        f"👤 <b>Имя:</b> {nick_tg(target)}\n"
        f"🔗 <b>Username:</b> {safe_username(target)}\n"
        f"🎖 <b>Ранг:</b> {rank_label(u['rank'])}\n"
        f"📛 <b>Псевдоним:</b> {u['nickname'] or '—'}\n"
        f"💬 <b>Сообщений:</b> {u['messages']}\n"
        f"⚠️ <b>Варнов:</b> {u['warns']}"
    )
    bot.reply_to(message, text)


@bot.message_handler(commands=["rules"])
def cmd_rules(message):
    bot.reply_to(message, f"📜 <a href='{Config.RULES_URL}'>Правила</a>")


@bot.message_handler(commands=["info"])
def cmd_info(message):
    bot.reply_to(message, "🤖 Бот анонимной поддержки «Разговоры по душам».")


@bot.message_handler(commands=["close"])
def cmd_close(message):
    # Закрытие заявки через reply в группе
    if message.chat.id in (Config.SUPPORT_GROUP, Config.TECH_GROUP) and message.reply_to_message:
        rt = message.reply_to_message
        if rt.from_user.id != bot.get_me().id:
            return
        r = db.get_reply(rt.message_id)
        if not r:
            return
        target = r["user_id"]
        tid = r["ticket_id"]

        if message.chat.id == Config.SUPPORT_GROUP:
            db.close_ticket(tid)
            try:
                bot.send_message(target,
                    f"✔️ <b>Обращение #{tid} закрыто администратором.</b>\n\n"
                    f"Главное меню:",
                    reply_markup=main_menu_kb())
            except Exception:
                pass
        else:
            db.close_tech_ticket(tid)
            try:
                bot.send_message(target, f"✔️ Обращение #{tid} закрыто.")
            except Exception:
                pass
        bot.reply_to(message, f"✅ Обращение #{tid} закрыто")
        return

    # Юзер в ЛС
    if message.chat.type == "private":
        uid = message.from_user.id
        t = db.get_open_ticket(uid)
        if t:
            db.close_ticket(t["ticket_id"])
            bot.send_message(uid, "🔚 Обращение закрыто.", reply_markup=main_menu_kb())
        else:
            bot.send_message(uid, "❌ Нет активного обращения.")


# ══════════════════════════════════════════════════════
# /check
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["check"])
def cmd_check(message):
    if rank_of(message.from_user.id) < db.get_perm("check", 1):
        return bot.reply_to(message, "❌ Недостаточно прав!")
    if not message.reply_to_message:
        return bot.reply_to(message, "Ответьте этой командой на сообщение")
    target = resolve_user(message, "")
    if not target:
        return
    u = db.get_user(target)
    bot.reply_to(message,
        f"🔍 <b>Инфо</b>\n"
        f"👤 Ник: {nick_tg(target)}\n"
        f"🔗 Username: {safe_username(target)}\n"
        f"🆔 <code>{target}</code>\n"
        f"🎖 Ранг: {rank_label(u['rank'])}\n"
        f"📛 Псевдоним: {u['nickname'] or '—'}")


# ══════════════════════════════════════════════════════
# /setrole
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["setrole"])
def cmd_setrole(message):
    if not check_access(message, db.get_perm("setrole", Config.MIN_SETROLE)):
        return

    text = message.text.partition(" ")[2].strip()
    target, rank, nickname = None, None, None

    if message.reply_to_message:
        target = resolve_user(message, "")
        parts = text.split(maxsplit=1)
        if not parts:
            return bot.reply_to(message, "Выберите номер ранга (1-8)")
        try:
            rank = int(parts[0])
        except ValueError:
            return bot.reply_to(message, "❌ Ранг 1–8")
        if len(parts) > 1 and parts[1].strip().startswith("#"):
            nickname = parts[1].strip()[1:]
    else:
        parts = text.split(maxsplit=2)
        if not parts:
            return bot.reply_to(message, "Укажите @user / ID / reply")
        target = resolve_user(message, parts[0])
        if not target:
            return bot.reply_to(message, "Пользователь не найден")
        if len(parts) < 2:
            return bot.reply_to(message, "Укажите ранг (1-8)")
        try:
            rank = int(parts[1])
        except ValueError:
            return bot.reply_to(message, "❌ Ранг 1–8")
        if len(parts) > 2 and parts[2].strip().startswith("#"):
            nickname = parts[2].strip()[1:]

    if not nickname:
        return bot.reply_to(message, "Укажите #псевдоним")
    if not (1 <= rank <= 8):
        return bot.reply_to(message, "❌ Ранг 1–8")

    my = rank_of(message.from_user.id)
    if rank >= my and message.from_user.id != Config.DEVELOPER_ID:
        return bot.reply_to(message, "❌ Нельзя выдать ранг выше своего")

    db.set_rank(target, rank, nickname)
    db.add_log("setrole", message.from_user.id, target, f"rank={rank} nick={nickname}")

    # В группе — новое сообщение
    bot.reply_to(message,
        f"👮 Администратор {safe_username(message.from_user.id)} "
        f"({nick_tg(message.from_user.id)}) назначил "
        f"{RANKS.get(rank, 'Неизвестно')} "
        f"{safe_username(target)} ({nick_tg(target)})")

    # В ЛС юзеру — новое сообщение
    try:
        bot.send_message(target,
            f"Вас назначили на {RANKS.get(rank, 'Неизвестно')} "
            f"с псевдонимом #{nickname}")
    except Exception:
        pass


# ══════════════════════════════════════════════════════
# /removerole
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["removerole"])
def cmd_removerole(message):
    if not check_access(message, db.get_perm("removerole", Config.MIN_REMOVEROLE)):
        return
    arg = message.text.partition(" ")[2].strip()
    target = resolve_user(message, arg)
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")

    old_rank = RANKS.get(db.get_user(target)["rank"], "—")
    db.remove_role(target)
    db.add_log("removerole", message.from_user.id, target, f"old_rank={old_rank}")

    # В группе
    bot.reply_to(message,
        f"👮 Администратор {safe_username(message.from_user.id)} "
        f"({nick_tg(message.from_user.id)}) снял роль с "
        f"{safe_username(target)} ({nick_tg(target)})\n"
        f"🎭 Бывший ранг: {old_rank}")

    # В ЛС
    try:
        bot.send_message(target,
            f"С вас сняли роль.\n"
            f"Бывший ранг: {old_rank}")
    except Exception:
        pass


# ══════════════════════════════════════════════════════
# /ban /unban /warn /unwarn /kick /mute /unmute
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["ban"])
def cmd_ban(message):
    if not check_access(message, db.get_perm("ban", Config.MIN_BAN)):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    db.set_ban(target, 1, "по решению администрации")
    bot.reply_to(message, f"🚫 {nick_tg(target)} забанен")


@bot.message_handler(commands=["unban"])
def cmd_unban(message):
    if not check_access(message, db.get_perm("unban", Config.MIN_UNBAN)):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    db.set_ban(target, 0, "")
    bot.reply_to(message, f"✅ {nick_tg(target)} разбанен")


@bot.message_handler(commands=["warn"])
def cmd_warn(message):
    if not check_access(message, db.get_perm("warn", Config.MIN_WARN)):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    u = db.get_user(target)
    warns = (u["warns"] or 0) + 1
    db.set_warns(target, warns)
    bot.reply_to(message, f"⚠️ {nick_tg(target)} — варн {warns}/3")
    if warns >= 3:
        db.set_ban(target, 1, "3 варна")
        bot.send_message(Config.SUPPORT_GROUP, f"🚫 Автобан {nick_tg(target)} за 3 варна")


@bot.message_handler(commands=["unwarn"])
def cmd_unwarn(message):
    if not check_access(message, db.get_perm("unwarn", Config.MIN_UNWARN)):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    u = db.get_user(target)
    warns = max(0, (u["warns"] or 0) - 1)
    db.set_warns(target, warns)
    bot.reply_to(message, f"✅ Варн снят, осталось: {warns}")


@bot.message_handler(commands=["kick"])
def cmd_kick(message):
    if not check_access(message, db.get_perm("kick", Config.MIN_KICK)):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    db.set_ban(target, 1, "кик")
    bot.reply_to(message, f"👢 {nick_tg(target)} кикнут")


@bot.message_handler(commands=["mute"])
def cmd_mute(message):
    if not check_access(message, db.get_perm("mute", Config.MIN_MUTE)):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    db.set_user(target, muted_until=time.time() + 3600)
    bot.reply_to(message, f"🔇 {nick_tg(target)} замучен на 1 час")


@bot.message_handler(commands=["unmute"])
def cmd_unmute(message):
    if not check_access(message, db.get_perm("unmute", Config.MIN_UNMUTE)):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    db.set_user(target, muted_until=0)
    bot.reply_to(message, f"🔊 {nick_tg(target)} размучен")


# ══════════════════════════════════════════════════════
# /botstats /logs /broadcast
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["botstats"])
def cmd_botstats(message):
    if rank_of(message.from_user.id) < db.get_perm("botstats", Config.MIN_BOTSTATS):
        return bot.reply_to(message, "❌ Недостаточно прав!")
    s = db.get_stats()
    me = bot.get_me()
    bot.reply_to(message,
        f"📊 <b>Статистика</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🤖 @{me.username}\n"
        f"👥 Всего: <b>{s['total']}</b>\n"
        f"👮 Админов: <b>{s['admins']}</b>\n"
        f"🟢 Активных: <b>{s['active']}</b>\n"
        f"🚫 Забанено: <b>{s['banned']}</b>\n"
        f"✉️ Сообщений: <b>{s['total_messages']}</b>\n"
        f"⚠️ Варнов: <b>{s['total_warns']}</b>")


@bot.message_handler(commands=["logs"])
def cmd_logs(message):
    if rank_of(message.from_user.id) < db.get_perm("logs", Config.MIN_LOGS):
        return bot.reply_to(message, "❌ Недостаточно прав!")
    rows = db.get_logs(20)
    if not rows:
        return bot.reply_to(message, "📭 Логов нет")
    text = "📋 <b>Последние действия</b>\n━━━━━━━━━━━━━━━━━━\n"
    for r in rows:
        text += f"• {r['date']} | {r['action']}\n"
    bot.reply_to(message, text)


@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(message):
    if rank_of(message.from_user.id) < db.get_perm("broadcast", Config.MIN_BROADCAST):
        return bot.reply_to(message, "❌ Недостаточно прав!")
    text = message.text.partition(" ")[2].strip()
    if not text:
        return bot.reply_to(message, "Формат: /broadcast [текст]")
    users = db.get_all_users()
    sent, failed = 0, 0
    for u in users:
        try:
            bot.send_message(u["user_id"], f"📢 {text}")
            sent += 1
            time.sleep(0.05)
        except Exception:
            failed += 1
    bot.reply_to(message, f"✅ Отправлено: {sent}, ошибок: {failed}")


# ══════════════════════════════════════════════════════
# СООБЩЕНИЯ ЮЗЕРА В ГРУППУ + ОТВЕТЫ АДМИНА
# ══════════════════════════════════════════════════════
@bot.message_handler(content_types=[
    "text", "photo", "video", "animation", "voice", "sticker",
    "video_note", "document", "audio"
])
def handle_messages(message):
    chat = message.chat.id
    uid = message.from_user.id

    if message.text and message.text.startswith("/"):
        return

    # reply в группе бесов
    if chat == Config.SUPPORT_GROUP and message.reply_to_message:
        rt = message.reply_to_message
        if rt.from_user.id != bot.get_me().id:
            return
        r = db.get_reply(rt.message_id)
        if not r:
            return
        target = r["user_id"]
        tid = r["ticket_id"]
        try:
            bot.send_message(target, f"✔️ <b>Ответ на обращение #{tid}</b>")
            bot.copy_message(target, chat, message.message_id)
        except Exception as e:
            bot.reply_to(message, f"❌ Не доставлено: {e}")
        return

    # reply в тех.отделе
    if chat == Config.TECH_GROUP and message.reply_to_message:
        rt = message.reply_to_message
        if rt.from_user.id != bot.get_me().id:
            return
        r = db.get_reply(rt.message_id)
        if not r:
            return
        target = r["user_id"]
        tid = r["ticket_id"]
        try:
            bot.send_message(target, f"✔️ <b>Ответ на обращение #{tid}</b>")
            bot.copy_message(target, chat, message.message_id)
        except Exception as e:
            bot.reply_to(message, f"❌ Не доставлено: {e}")
        return

    # ЛС
    if message.chat.type == "private":
        u = db.get_user(uid)
        if u["banned"]:
            return
        if is_flood(uid):
            return
        if message.from_user.username:
            db.set_user(uid, username=message.from_user.username)
        db.set_user(uid, messages=(u["messages"] or 0) + 1)

        # Бес-обращение
        t = db.get_open_ticket(uid)
        if t:
            try:
                sent = bot.send_message(Config.SUPPORT_GROUP,
                    f"📩 <b>Сообщение от {u['pseudo'] or uid}</b>\n"
                    f"🎫 Заявка #{t['ticket_id']}")
                bot.copy_message(Config.SUPPORT_GROUP, chat, message.message_id)
                db.save_reply(sent.message_id, uid, t["ticket_id"])
            except Exception as e:
                print(f"[forward] {e}")
            return

        # Тех-обращение
        tt = db.get_open_tech_ticket(uid)
        if tt:
            try:
                sent = bot.send_message(Config.TECH_GROUP,
                    f"📩 <b>Сообщение</b>\n"
                    f"🎫 Обращение #{tt['ticket_id']}\n"
                    f"🆔 <code>{uid}</code>")
                bot.copy_message(Config.TECH_GROUP, chat, message.message_id)
                db.save_reply(sent.message_id, uid, tt["ticket_id"])
            except Exception as e:
                print(f"[forward tech] {e}")
            return


# ══════════════════════════════════════════════════════
# ЗАПУСК
# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🤖 Бот запущен...")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)