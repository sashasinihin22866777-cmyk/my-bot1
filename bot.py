# -*- coding: utf-8 -*-
"""
Telegram-бот «Секретарь» (Livegram-стиль)
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
        "8934743448:AAFPaZ_rcCLAyWcqrgZjYSS3hgsmNQtsVKU"
    )
    DEVELOPER_ID = 963549015
    SUPPORT_GROUP = -1004249566422
    CLAIMS_GROUP = -1004311016312
    COMMANDS_GROUP = -1004436484199
    DB_PATH = "/tmp/secretary.db"

    MIN_SETROLE = 5
    MIN_REMOVEROLE = 5
    MIN_BAN = 5
    MIN_UNBAN = 5
    MIN_WARN = 5
    MIN_UNWARN = 5
    MIN_PBAN = 8
    MIN_PUNBAN = 8
    MIN_TAKE = 1
    MIN_CHECK = 1
    MIN_RANKS = 1
    MIN_APPEAL_DECIDE = 8
    MIN_SETWELCOME = 8
    MIN_ANSWER = 1
    MIN_NOTE = 5
    MIN_LOGS = 8
    MIN_BROADCAST = 8

    APPEAL_COOLDOWN = 24 * 3600
    FLOOD_INTERVAL = 2
    MUTE_TIME = 30
    WARN_LIMIT = 3


RANKS = {
    0:   "Пользователь",
    1:   "Администратор",
    2:   "Младший администратор бота",
    3:   "Администратор бота",
    4:   "Старший администратор бота",
    5:   "Заместитель совладельца бота",
    6:   "Заместитель владельца бота",
    7:   "Совладелец бота",
    8:   "Владелец бота",
    100: "Разработчик бота",
}

APPEAL_QUESTIONS = [
    "Ваш юзернейм/id?",
    "За что вы были заблокированы?",
    "Как вы это исправите?",
    "Почему мы должны вас разблокировать?",
]


# ══════════════════════════════════════════════════════
# ХРАНИЛИЩЕ
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
                    rank INTEGER DEFAULT 0,
                    nickname TEXT DEFAULT NULL,
                    username TEXT DEFAULT NULL,
                    warns INTEGER DEFAULT 0,
                    messages INTEGER DEFAULT 0,
                    joined TEXT DEFAULT NULL,
                    last_msg REAL DEFAULT 0,
                    muted_until REAL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS bans (
                    user_id INTEGER PRIMARY KEY,
                    banned_by INTEGER,
                    until INTEGER DEFAULT -1,
                    reason TEXT DEFAULT 'не указана',
                    pban INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS tickets (
                    user_id INTEGER PRIMARY KEY,
                    admin_id INTEGER
                );
                CREATE TABLE IF NOT EXISTS replies (
                    admin_msg_id INTEGER PRIMARY KEY,
                    user_id INTEGER
                );
                CREATE TABLE IF NOT EXISTS appeals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    answers TEXT,
                    status TEXT DEFAULT 'pending',
                    created TEXT,
                    msg_id INTEGER
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_id INTEGER,
                    admin_id INTEGER,
                    text TEXT,
                    date TEXT
                );
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT,
                    admin_id INTEGER,
                    target_id INTEGER,
                    details TEXT,
                    date TEXT
                );
            """)
            c.execute("INSERT OR IGNORE INTO settings VALUES('welcome', '👋 Добро пожаловать!')")
            c.execute("INSERT OR IGNORE INTO settings VALUES('rules', '📜 Правила бота пока не установлены.')")
            c.execute("INSERT OR IGNORE INTO settings VALUES('info', '🤖 Информация о боте пока не задана.')")
            c.execute("INSERT OR IGNORE INTO settings VALUES('gwelcome', '🖤 Добро пожаловать в обитель теней, {name}!')")
            c.execute("INSERT OR IGNORE INTO users(user_id, rank, nickname) VALUES(?, ?, ?)",
                      (Config.DEVELOPER_ID, 100, 'Разработчик'))
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

    def set_rank(self, uid, rank, nickname=None):
        self._exec("UPDATE users SET rank=?, nickname=? WHERE user_id=?",
                   (int(rank), nickname, uid))

    def remove_role(self, uid):
        self._exec("UPDATE users SET rank=0, nickname=NULL WHERE user_id=?", (uid,))

    def set_username(self, uid, username):
        self._exec("UPDATE users SET username=? WHERE user_id=?", (username, uid))

    def inc_messages(self, uid):
        self._exec("UPDATE users SET messages=messages+1 WHERE user_id=?", (uid,))

    def set_last_msg(self, uid, t):
        self._exec("UPDATE users SET last_msg=? WHERE user_id=?", (t, uid))

    def set_muted(self, uid, until):
        self._exec("UPDATE users SET muted_until=? WHERE user_id=?", (until, uid))

    def set_warns(self, uid, count):
        self._exec("UPDATE users SET warns=? WHERE user_id=?", (count, uid))

    def get_ban(self, uid):
        row = self._exec("SELECT * FROM bans WHERE user_id=?", (uid,), "one")
        if not row:
            return None
        if row["until"] != -1 and row["until"] < int(time.time()):
            return None
        return row

    def set_ban(self, uid, by, reason, until):
        old = self._exec("SELECT pban FROM bans WHERE user_id=?", (uid,), "one")
        pban = old["pban"] if old else 0
        self._exec("REPLACE INTO bans VALUES(?, ?, ?, ?, ?)",
                   (uid, by, until, reason, pban))

    def remove_ban(self, uid):
        self._exec("DELETE FROM bans WHERE user_id=?", (uid,))

    def set_pban(self, uid, state):
        old = self._exec("SELECT user_id FROM bans WHERE user_id=?", (uid,), "one")
        if old:
            self._exec("UPDATE bans SET pban=? WHERE user_id=?", (1 if state else 0, uid))
        else:
            self._exec("INSERT INTO bans(user_id, pban) VALUES(?, ?)", (uid, 1 if state else 0))

    def create_ticket(self, uid, admin_id):
        self._exec("REPLACE INTO tickets VALUES(?, ?)", (uid, admin_id))

    def delete_ticket(self, uid):
        self._exec("DELETE FROM tickets WHERE user_id=?", (uid,))

    def get_ticket(self, uid):
        row = self._exec("SELECT admin_id FROM tickets WHERE user_id=?", (uid,), "one")
        return row["admin_id"] if row else None

    def get_all_tickets(self):
        return self._exec("SELECT user_id, admin_id FROM tickets", fetch="all") or []

    def clear_tickets(self):
        self._exec("DELETE FROM tickets")

    def save_reply(self, msg_id, uid):
        self._exec("REPLACE INTO replies VALUES(?, ?)", (msg_id, uid))

    def get_reply_user(self, msg_id):
        row = self._exec("SELECT user_id FROM replies WHERE admin_msg_id=?", (msg_id,), "one")
        return row["user_id"] if row else None

    def add_appeal(self, uid, answers):
        return self._exec(
            "INSERT INTO appeals(user_id, answers, created) VALUES(?, ?, ?)",
            (uid, "|".join(answers), str(time.time())))

    def set_appeal_msg(self, appeal_id, msg_id):
        self._exec("UPDATE appeals SET msg_id=? WHERE id=?", (msg_id, appeal_id))

    def get_appeal(self, appeal_id):
        return self._exec("SELECT * FROM appeals WHERE id=?", (appeal_id,), "one")

    def update_appeal_status(self, appeal_id, status):
        self._exec("UPDATE appeals SET status=? WHERE id=?", (status, appeal_id))

    def get_last_appeal_time(self, uid):
        row = self._exec(
            "SELECT created FROM appeals WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (uid,), "one")
        return float(row["created"]) if row else 0

    def get_setting(self, key, default=None):
        row = self._exec("SELECT value FROM settings WHERE key=?", (key,), "one")
        return row["value"] if row else default

    def set_setting(self, key, value):
        self._exec("REPLACE INTO settings VALUES(?, ?)", (key, value))

    def add_note(self, target, admin, text):
        self._exec("INSERT INTO notes(target_id, admin_id, text, date) VALUES(?, ?, ?, ?)",
                   (target, admin, text, time.strftime("%d.%m.%Y %H:%M")))

    def get_notes(self, target):
        return self._exec("SELECT * FROM notes WHERE target_id=? ORDER BY id DESC",
                          (target,), "all") or []

    def clear_notes(self, target):
        self._exec("DELETE FROM notes WHERE target_id=?", (target,))

    def add_log(self, action, admin_id=None, target_id=None, details=""):
        self._exec(
            "INSERT INTO logs(action, admin_id, target_id, details, date) VALUES(?, ?, ?, ?, ?)",
            (action, admin_id, target_id, details, time.strftime("%d.%m.%Y %H:%M:%S")))

    def get_logs(self, limit=10):
        return self._exec("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,), "all") or []

    def get_top_users(self, limit=10):
        return self._exec(
            "SELECT user_id, messages, rank FROM users ORDER BY messages DESC LIMIT ?",
            (limit,), "all") or []

    def get_all_users(self):
        return self._exec("SELECT user_id FROM users", fetch="all") or []


# ══════════════════════════════════════════════════════
# ИНИЦИАЛИЗАЦИЯ
# ══════════════════════════════════════════════════════
bot = telebot.TeleBot(Config.TOKEN, parse_mode="HTML")
db = Storage(Config.DB_PATH)

try:
    bot.remove_webhook(drop_pending_updates=True)
    print("✅ Webhook удалён")
except Exception as e:
    print(f"⚠️ Webhook: {e}")

appeal_sessions = {}


# ══════════════════════════════════════════════════════
# ХЕЛПЕРЫ
# ══════════════════════════════════════════════════════
def rank_of(uid):
    if uid == Config.DEVELOPER_ID:
        return 100
    return db.get_user(uid)["rank"]


def rank_label(uid):
    r = rank_of(uid)
    if r == 100:
        return "⚙️ Разработчик бота"
    if r == 0:
        return "👤 Пользователь"
    return f"🛡 {RANKS.get(r, 'Неизвестно')}"


def nick_of(uid):
    return db.get_user(uid)["nickname"] or f"ID{uid}"


def nick_tg(uid):
    try:
        u = bot.get_chat(uid)
        return u.first_name or f"ID{uid}"
    except Exception:
        return f"ID{uid}"


def admin_pseudo(uid):
    nick = db.get_user(uid)["nickname"]
    if nick:
        return f"#{nick}"
    return "#Администратор"


def safe_username(uid):
    u_data = db.get_user(uid)
    if u_data["username"]:
        return f"@{u_data['username']}"
    try:
        u = bot.get_chat(uid)
        return f"@{u.username}" if u.username else "без username"
    except Exception:
        return "без username"


def check_access(message, min_rank):
    if rank_of(message.from_user.id) < min_rank:
        bot.reply_to(message, "❌ Недостаточно прав!")
        return False
    return True


def is_flood(uid):
    u = db.get_user(uid)
    now = time.time()
    if u["muted_until"] and now < u["muted_until"]:
        return True
    if u["last_msg"] and now - u["last_msg"] < Config.FLOOD_INTERVAL:
        db.set_muted(uid, now + Config.MUTE_TIME)
        return True
    db.set_last_msg(uid, now)
    return False


def parse_period(s):
    if not s or s == "-1":
        return -1
    try:
        num = int(s[:-1])
        unit = s[-1].lower()
        mult = {"h": 3600, "d": 86400, "m": 2592000, "y": 31536000}.get(unit)
        if not mult:
            return -1
        return int(time.time()) + num * mult
    except Exception:
        return -1


def format_until(until):
    if until == -1:
        return "навсегда"
    if until == 0:
        return "—"
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(until))


def resolve_user(message, text):
    if message.reply_to_message:
        rt = message.reply_to_message
        if rt.from_user.id == bot.get_me().id:
            uid = db.get_reply_user(rt.message_id)
            if uid:
                return uid
        return rt.from_user.id
    if not text:
        return None
    arg = text.strip().split()[0] if text.strip() else ""
    if arg.isdigit():
        return int(arg)
    if arg.startswith("@"):
        try:
            return bot.get_chat(arg).id
        except Exception:
            return None
    if "t.me/" in arg:
        try:
            uname = arg.split("t.me/")[1].split("/")[0].split("?")[0]
            return bot.get_chat("@" + uname).id
        except Exception:
            return None
    return None


def send_to_user(uid, text, kb=None):
    try:
        bot.send_message(uid, text, reply_markup=kb)
        return True
    except Exception as e:
        err = str(e)
        if "403" in err or "Forbidden" in err:
            print(f"[send_to_user {uid}] юзер не начинал диалог")
        else:
            print(f"[send_to_user {uid}] {e}")
        return False


def create_new_user_post(uid, category, gender):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ Взять", callback_data=f"take_{uid}"),
        types.InlineKeyboardButton("❌ Отказаться", callback_data=f"refuse_{uid}"),
    )
    text = (
        f"🆕 <b>Новый пользователь</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Никнейм:</b> {nick_tg(uid)}\n"
        f"📂 <b>Категория:</b> {category}\n"
        f"🚻 <b>Пол:</b> {gender}\n"
        f"🆔 <code>{uid}</code>"
    )
    try:
        sent = bot.send_message(Config.SUPPORT_GROUP, text, reply_markup=kb)
        db.save_reply(sent.message_id, uid)
        try:
            bot.pin_chat_message(Config.SUPPORT_GROUP, sent.message_id)
        except Exception as e:
            print(f"⚠️ pin: {e}")
    except Exception as e:
        print(f"❌ new_user_post: {e}")


# ══════════════════════════════════════════════════════
# ПРИВЕТСТВИЕ АДМИНОВ ПРИ ВХОДЕ В ГРУППУ
# ══════════════════════════════════════════════════════
@bot.message_handler(content_types=["new_chat_members"])
def on_new_member(message):
    if message.chat.id != Config.SUPPORT_GROUP:
        return
    for new_member in message.new_chat_members:
        if new_member.id == bot.get_me().id:
            continue
        if rank_of(new_member.id) < 1:
            continue
        template = db.get_setting(
            "gwelcome",
            "🖤 Добро пожаловать в обитель теней, {name}!"
        )
        mention = f'<a href="tg://user?id={new_member.id}">{new_member.first_name}</a>'
        text = template.replace("{name}", mention)
        try:
            bot.send_message(Config.SUPPORT_GROUP, text)
        except Exception as e:
            print(f"[gwelcome] {e}")


# ══════════════════════════════════════════════════════
# /help
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["help"])
def cmd_help(message):
    uid = message.from_user.id
    r = rank_of(uid)
    text = "📖 <b>Команды</b>\n\n"
    text += "<b>👤 Для всех:</b>\n"
    text += "/start — приветствие\n"
    text += "/help — это меню\n"
    text += "/stats — профиль\n"
    text += "/close — завершить диалог\n"
    text += "/rules — правила\n"
    text += "/info — о боте\n\n"

    if r >= Config.MIN_RANKS:
        text += "<b>🛠 Ранг 1+:</b>\n"
        text += "/ranks — список рангов\n"
        text += "/check — инфо о юзере (reply)\n"
        text += "/top — топ юзеров\n\n"

    if r >= Config.MIN_SETROLE:
        text += "<b>🧑‍💼 Ранг 5+:</b>\n"
        text += "/setrole @user N #ник\n"
        text += "/removerole @user\n"
        text += "/ban @user [период] [причина]\n"
        text += "/warn @user\n"
        text += "/unwarn @user\n"
        text += "/kick @user\n"
        text += "/mute @user [7d]\n"
        text += "/unmute @user\n"
        text += "/dialogs / /dialog @user\n"
        text += "/note @user <текст> / /notes @user\n\n"

    if r >= Config.MIN_PBAN:
        text += "<b>👑 Ранг 8+:</b>\n"
        text += "/unban @user\n"
        text += "/pban / /punban @user\n"
        text += "/setwelcome <текст>\n"
        text += "/setrules <текст>\n"
        text += "/setinfo <текст>\n"
        text += "/setgwelcome <текст> — приветствие админов\n"
        text += "/clearwarns @user\n"
        text += "/broadcast <текст>\n"
        text += "/logs [N]\n\n"

    if r >= 100:
        text += "<b>⚙️ Разработчик:</b>\n"
        text += "/setowner @user\n"
        text += "/cleardialogs\n"

    bot.reply_to(message, text)


# ══════════════════════════════════════════════════════
# /rules / setrules / info / setinfo / setgwelcome
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["rules"])
def cmd_rules(message):
    rules = db.get_setting("rules", "📜 Правила пока не заданы.")
    bot.reply_to(message, rules)


@bot.message_handler(commands=["setrules"])
def cmd_setrules(message):
    if not check_access(message, Config.MIN_SETWELCOME):
        return
    text = message.text.partition(" ")[2].strip()
    if not text:
        return bot.reply_to(message, "Формат: /setrules <текст>")
    db.set_setting("rules", text)
    db.add_log("setrules", message.from_user.id)
    bot.reply_to(message, "✅ Правила обновлены")


@bot.message_handler(commands=["info"])
def cmd_info(message):
    info = db.get_setting("info", "🤖 Информация о боте пока не задана.")
    bot.reply_to(message, info)


@bot.message_handler(commands=["setinfo"])
def cmd_setinfo(message):
    if not check_access(message, Config.MIN_SETWELCOME):
        return
    text = message.text.partition(" ")[2].strip()
    if not text:
        return bot.reply_to(message, "Формат: /setinfo <текст>")
    db.set_setting("info", text)
    db.add_log("setinfo", message.from_user.id)
    bot.reply_to(message, "✅ Информация о боте обновлена")


@bot.message_handler(commands=["setgwelcome"])
def cmd_setgwelcome(message):
    if not check_access(message, Config.MIN_SETWELCOME):
        return
    text = message.text.partition(" ")[2].strip()
    if not text:
        return bot.reply_to(message,
            "Формат: <code>/setgwelcome <текст></code>\n"
            "Используйте <code>{name}</code> для подстановки имени.\n\n"
            "Пример:\n"
            "<code>/setgwelcome 🖤 Добро пожаловать, {name}!</code>")
    db.set_setting("gwelcome", text)
    db.add_log("setgwelcome", message.from_user.id)
    bot.reply_to(message,
        "✅ Приветствие для админов обновлено\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{text}")


# ══════════════════════════════════════════════════════
# /close
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["close"])
def cmd_close(message):
    chat = message.chat.id
    uid = message.from_user.id

    if chat == Config.SUPPORT_GROUP and message.reply_to_message:
        if rank_of(uid) < Config.MIN_ANSWER:
            return bot.reply_to(message, "❌ Недостаточно прав!")
        rt = message.reply_to_message
        target = db.get_reply_user(rt.message_id) if rt.from_user.id == bot.get_me().id else rt.from_user.id
        if not target:
            return bot.reply_to(message, "❌ Не удалось определить пользователя")
        if not db.get_ticket(target):
            return bot.reply_to(message, "❌ У пользователя нет активного диалога")
        db.delete_ticket(target)
        db.add_log("close_dialog", uid, target)
        bot.reply_to(message,
            f"🔚 <b>Диалог завершён командой</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👮 <b>Администратор:</b> {admin_pseudo(uid)}\n"
            f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
            f"🆔 <code>{target}</code>")
        send_to_user(target,
            "🔚 <b>Диалог завершён</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Администратор завершил диалог.\n\n"
            "<i>Если снова понадобится помощь — нажмите /start</i>")
        return

    if message.chat.type == "private":
        admin_id = db.get_ticket(uid)
        if not admin_id:
            return bot.send_message(uid,
                "❌ У вас нет активного диалога.\nНажмите /start чтобы начать новый.")
        db.delete_ticket(uid)
        db.add_log("close_dialog_user", uid)
        bot.send_message(uid,
            "🔚 <b>Диалог завершён</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<i>Если снова понадобится помощь — нажмите /start</i>")
        try:
            bot.send_message(Config.SUPPORT_GROUP,
                f"🔚 <b>Пользователь завершил диалог</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Пользователь:</b> {nick_tg(uid)}\n"
                f"🆔 <code>{uid}</code>")
        except Exception:
            pass


# ══════════════════════════════════════════════════════
# /start
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["start"])
def cmd_start(message):
    if message.chat.type != "private":
        return
    uid = message.from_user.id
    db.get_user(uid)

    ban = db.get_ban(uid)
    if ban:
        period = format_until(ban["until"])
        text = (
            f"🚫 <b>Вы заблокированы в боте</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏳ <b>Срок:</b> {period}\n"
            f"📋 <b>Причина:</b> {ban['reason']}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<i>Если не согласны — нажмите кнопку ниже.</i>"
        )
        if not ban["pban"]:
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("📩 Обжаловать наказание", callback_data="appeal_start"))
            bot.send_message(uid, text, reply_markup=kb)
        else:
            bot.send_message(uid, text)
        return

    welcome = db.get_setting("welcome", "👋 Добро пожаловать!")
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📞 Позвать администратора", callback_data="call_admin"),
        types.InlineKeyboardButton("📊 Мой профиль", callback_data="show_profile"),
        types.InlineKeyboardButton("📜 Правила", callback_data="show_rules"),
    )
    bot.send_message(uid, welcome, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "show_profile")
def cb_show_profile(call):
    uid = call.from_user.id
    u = db.get_user(uid)
    r = rank_of(uid)
    text = (
        f"📊 <b>Профиль</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"👤 <b>Имя:</b> {nick_tg(uid)}\n"
        f"🔗 <b>Username:</b> {safe_username(uid)}\n"
    )
    if r >= 1:
        text += f"🎖 <b>Должность:</b> {RANKS.get(r, 'Неизвестно')}\n"
        text += f"📛 <b>Псевдоним:</b> {u['nickname'] or '—'}\n"
    text += f"💬 <b>Сообщений:</b> {u['messages']}\n"
    text += f"⚠️ <b>Варнов:</b> {u['warns']}"
    bot.send_message(uid, text)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data == "show_rules")
def cb_show_rules(call):
    rules = db.get_setting("rules", "📜 Правила пока не заданы.")
    bot.send_message(call.from_user.id, rules)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data == "call_admin")
def cb_call_admin(call):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🖤 Поддержка", callback_data="cat_Поддержка"),
        types.InlineKeyboardButton("💬 Общение", callback_data="cat_Общение"),
        types.InlineKeyboardButton("🪛 Универсал", callback_data="cat_Универсал"),
    )
    bot.edit_message_text("📂 <b>Выберите категорию</b>",
                          call.message.chat.id, call.message.message_id,
                          reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("cat_"))
def cb_category(call):
    category = call.data.split("_", 1)[1]
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🖤 Мальчик", callback_data=f"gen_{category}_Мальчик"),
        types.InlineKeyboardButton("❤️ Девочка", callback_data=f"gen_{category}_Девочка"),
    )
    bot.edit_message_text("🚻 <b>Выберите пол администратора</b>",
                          call.message.chat.id, call.message.message_id,
                          reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("gen_"))
def cb_gender(call):
    _, category, gender = call.data.split("_", 2)
    uid = call.from_user.id

    if db.get_ticket(uid):
        return bot.edit_message_text(
            "⏳ У вас уже есть активный диалог с администратором.",
            call.message.chat.id, call.message.message_id)

    bot.edit_message_text(
        "⏳ <b>Вам ответят как только появится свободный администратор!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "<i>Ожидайте.</i>",
        call.message.chat.id, call.message.message_id)
    create_new_user_post(uid, category, gender)


# ══════════════════════════════════════════════════════
# ВЗЯТЬ / ОТКАЗАТЬСЯ
# ══════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data.startswith("take_"))
def cb_take(call):
    admin_uid = call.from_user.id
    if rank_of(admin_uid) < Config.MIN_TAKE:
        return bot.answer_callback_query(call.id, "❌ Недостаточно прав!", show_alert=True)
    try:
        target = int(call.data.split("_", 1)[1])
    except Exception:
        return bot.answer_callback_query(call.id, "Ошибка данных")

    try:
        bot.unpin_chat_message(Config.SUPPORT_GROUP, call.message.message_id)
    except Exception:
        pass
    try:
        bot.edit_message_reply_markup(Config.SUPPORT_GROUP, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    kb_group = types.InlineKeyboardMarkup()
    kb_group.add(types.InlineKeyboardButton("🔚 Закрыть диалог", callback_data=f"close_{target}"))
    bot.send_message(
        Config.SUPPORT_GROUP,
        f"✅ <b>Заявка принята</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮 <b>Администратор:</b> {admin_pseudo(admin_uid)}\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>",
        reply_markup=kb_group)

    db.create_ticket(target, admin_uid)
    db.add_log("take_user", admin_uid, target)

    kb_user = types.InlineKeyboardMarkup()
    kb_user.add(types.InlineKeyboardButton("🔚 Закрыть диалог", callback_data="user_close"))
    send_to_user(
        target,
        "✅ <b>Администратор принял вас</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💬 Пишите сообщения — они уйдут администратору анонимно.\n\n"
        "<i>Нажмите кнопку ниже, чтобы завершить диалог.</i>",
        kb=kb_user)
    bot.answer_callback_query(call.id, "Принято")


@bot.callback_query_handler(func=lambda c: c.data.startswith("refuse_"))
def cb_refuse(call):
    admin_uid = call.from_user.id
    if rank_of(admin_uid) < Config.MIN_TAKE:
        return bot.answer_callback_query(call.id, "❌ Недостаточно прав!", show_alert=True)
    try:
        target = int(call.data.split("_", 1)[1])
    except Exception:
        return bot.answer_callback_query(call.id, "Ошибка данных")

    try:
        bot.unpin_chat_message(Config.SUPPORT_GROUP, call.message.message_id)
    except Exception:
        pass
    try:
        bot.edit_message_reply_markup(Config.SUPPORT_GROUP, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    bot.send_message(Config.SUPPORT_GROUP,
        f"❌ <b>Заявка отклонена</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮 <b>Администратор:</b> {admin_pseudo(admin_uid)}\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>")
    db.add_log("refuse_user", admin_uid, target)
    send_to_user(target,
        "❌ <b>Заявка отклонена</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "<i>Используйте /start, чтобы попробовать снова.</i>")
    bot.answer_callback_query(call.id, "Отказ отправлен")


# ══════════════════════════════════════════════════════
# КНОПКИ ЗАКРЫТИЯ ДИАЛОГА
# ══════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data.startswith("close_"))
def cb_close_admin(call):
    uid = call.from_user.id
    if rank_of(uid) < Config.MIN_ANSWER:
        return bot.answer_callback_query(call.id, "❌ Недостаточно прав!", show_alert=True)
    try:
        target = int(call.data.split("_", 1)[1])
    except Exception:
        return bot.answer_callback_query(call.id, "Ошибка данных")

    if not db.get_ticket(target):
        return bot.answer_callback_query(call.id, "❌ Диалог уже закрыт", show_alert=True)

    db.delete_ticket(target)
    db.add_log("close_dialog_btn", uid, target)

    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    bot.send_message(Config.SUPPORT_GROUP,
        f"🔚 <b>Диалог завершён</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮 <b>Администратор:</b> {admin_pseudo(uid)}\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>")
    send_to_user(target,
        "🔚 <b>Диалог завершён</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Администратор завершил диалог.\n\n"
        "<i>Если снова понадобится помощь — нажмите /start</i>")
    bot.answer_callback_query(call.id, "Диалог закрыт")


@bot.callback_query_handler(func=lambda c: c.data == "user_close")
def cb_close_user(call):
    uid = call.from_user.id
    admin_id = db.get_ticket(uid)
    if not admin_id:
        return bot.answer_callback_query(call.id, "❌ У вас нет активного диалога", show_alert=True)

    db.delete_ticket(uid)
    db.add_log("close_dialog_user_btn", uid)

    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    bot.send_message(uid,
        "🔚 <b>Диалог завершён</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "<i>Если снова понадобится помощь — нажмите /start</i>")
    try:
        bot.send_message(Config.SUPPORT_GROUP,
            f"🔚 <b>Пользователь завершил диалог</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Пользователь:</b> {nick_tg(uid)}\n"
            f"🆔 <code>{uid}</code>")
    except Exception:
        pass

    bot.answer_callback_query(call.id, "Диалог закрыт")


# ══════════════════════════════════════════════════════
# /stats
# ══════════════════════════════════════════════════════
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
    r = rank_of(target)
    ban = db.get_ban(target)

    text = (
        f"📊 <b>Профиль</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ID:</b> <code>{target}</code>\n"
        f"👤 <b>Имя:</b> {nick_tg(target)}\n"
        f"🔗 <b>Username:</b> {safe_username(target)}\n"
    )
    if r >= 1:
        text += f"🎖 <b>Должность:</b> {RANKS.get(r, 'Неизвестно')}\n"
        text += f"📛 <b>Псевдоним:</b> {u['nickname'] or '—'}\n"
    text += f"💬 <b>Сообщений:</b> {u['messages']}\n"
    text += f"⚠️ <b>Варнов:</b> {u['warns']}\n"
    if u["joined"]:
        text += f"📅 <b>В боте с:</b> {u['joined']}\n"
    if ban:
        text += (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🚫 <b>Заблокирован</b>\n"
            f"⏳ <b>Срок:</b> {format_until(ban['until'])}\n"
            f"📋 <b>Причина:</b> {ban['reason']}"
        )
    bot.reply_to(message, text)


# ══════════════════════════════════════════════════════
# /ranks
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["ranks"])
def cmd_ranks(message):
    if not check_access(message, Config.MIN_RANKS):
        return
    text = "📊 <b>Список рангов</b>\n━━━━━━━━━━━━━━━━━━\n"
    for i in range(1, 9):
        text += f"<b>{i}</b> — {RANKS[i]}\n"
    if rank_of(message.from_user.id) >= 100:
        text += f"\n<b>100</b> — {RANKS[100]} (только разработчик)"
    bot.reply_to(message, text)


# ══════════════════════════════════════════════════════
# /setrole
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["setrole"])
def cmd_setrole(message):
    if not check_access(message, Config.MIN_SETROLE):
        return

    text = message.text.partition(" ")[2].strip()
    target, rank, nickname = None, None, None

    if message.reply_to_message:
        target = resolve_user(message, "")
        parts = text.split(maxsplit=1)
        if not parts:
            return bot.reply_to(message, "Выберите номер ранга (1-8) или 100\nИнформация: /ranks")
        try:
            rank = int(parts[0])
        except ValueError:
            return bot.reply_to(message, "❌ Ранг должен быть числом 1–8 или 100")
        if len(parts) > 1 and parts[1].strip().startswith("#"):
            nickname = parts[1].strip()[1:]
    else:
        parts = text.split(maxsplit=2)
        if not parts:
            return bot.reply_to(message,
                "❌ <b>Укажите цель</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "• reply на сообщение юзера: <code>/setrole 1 #ник</code>\n"
                "• по ID: <code>/setrole 123456789 1 #ник</code>\n"
                "• по @username (если юзер писал боту)")
        target = resolve_user(message, parts[0])
        if not target:
            return bot.reply_to(message,
                "❌ <b>Пользователь не найден</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Бот не может найти юзера по @username, если тот "
                "не писал боту.\n\n"
                "<b>Используйте:</b>\n"
                "• <b>reply</b> на сообщение: <code>/setrole 1 #ник</code>\n"
                "• по <b>ID</b>: <code>/setrole 123456789 1 #ник</code>")
        if len(parts) < 2:
            return bot.reply_to(message, "Выберите номер ранга (1-8) или 100\nИнформация: /ranks")
        try:
            rank = int(parts[1])
        except ValueError:
            return bot.reply_to(message, "❌ Ранг должен быть числом 1–8 или 100")
        if len(parts) > 2 and parts[2].strip().startswith("#"):
            nickname = parts[2].strip()[1:]

    if not nickname:
        return bot.reply_to(message, "Укажите #псевдоним")

    if rank == 100 and message.from_user.id != Config.DEVELOPER_ID:
        return bot.reply_to(message, "❌ Только разработчик может выдать ранг 100")

    if not ((1 <= rank <= 8) or rank == 100):
        return bot.reply_to(message, "Выберите номер ранга (1-8) или 100 (только разработчик)\nИнформация: /ranks")

    my = rank_of(message.from_user.id)
    if message.from_user.id != Config.DEVELOPER_ID and rank >= my:
        return bot.reply_to(message, "❌ Нельзя выдать ранг выше своего")

    db.set_rank(target, rank, nickname)
    db.add_log("setrole", message.from_user.id, target, f"rank={rank} nick={nickname}")

    bot.reply_to(message,
        f"🎖 <b>Роль назначена</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮 <b>Администратор:</b> {admin_pseudo(message.from_user.id)}\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>\n"
        f"🎭 <b>Ранг:</b> {RANKS.get(rank, 'Неизвестно')}\n"
        f"📛 <b>Псевдоним:</b> #{nickname}")
    send_to_user(target,
        f"🎖 <b>Вам выдана роль</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎭 <b>Ранг:</b> {RANKS.get(rank, 'Неизвестно')}\n"
        f"📛 <b>Псевдоним:</b> #{nickname}")


# ══════════════════════════════════════════════════════
# /removerole
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["removerole"])
def cmd_removerole(message):
    if not check_access(message, Config.MIN_REMOVEROLE):
        return
    arg = message.text.partition(" ")[2].strip()
    target = resolve_user(message, arg)
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    old_rank = RANKS.get(db.get_user(target)["rank"], "—")
    db.remove_role(target)
    db.add_log("removerole", message.from_user.id, target, f"old_rank={old_rank}")
    bot.reply_to(message,
        f"❌ <b>Роль снята</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮 <b>Администратор:</b> {admin_pseudo(message.from_user.id)}\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>\n"
        f"🎭 <b>Бывший ранг:</b> {old_rank}")
    send_to_user(target,
        f"❌ <b>С вас снята роль</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎭 <b>Бывший ранг:</b> {old_rank}")


# ══════════════════════════════════════════════════════
# /check
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["check"])
def cmd_check(message):
    if not check_access(message, Config.MIN_CHECK):
        return
    if not message.reply_to_message:
        return bot.reply_to(message, "Ответьте этой командой на сообщение пользователя")
    target = resolve_user(message, "")
    if not target:
        return bot.reply_to(message, "❌ Не удалось определить пользователя")
    bot.reply_to(message,
        f"🔍 <b>Информация</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Ник:</b> {nick_tg(target)}\n"
        f"🔗 <b>Юзернейм:</b> {safe_username(target)}\n"
        f"🆔 <b>ID:</b> <code>{target}</code>")


# ══════════════════════════════════════════════════════
# /setowner
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["setowner"])
def cmd_setowner(message):
    if message.from_user.id != Config.DEVELOPER_ID:
        return bot.reply_to(message, "❌ Только разработчик может назначать владельца.")
    arg = message.text.partition(" ")[2].strip()
    target = resolve_user(message, arg)
    if not target:
        return bot.reply_to(message, "Формат: /setowner @username | id | reply")
    db.set_rank(target, 8, "Владелец")
    db.add_log("setowner", message.from_user.id, target)
    bot.reply_to(message,
        f"👑 <b>Владелец назначен</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>")
    send_to_user(target,
        "👑 <b>Вас назначили владельцем бота</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🎭 <b>Ранг:</b> Владелец")


# ══════════════════════════════════════════════════════
# /ban /unban
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["ban"])
def cmd_ban(message):
    if not check_access(message, Config.MIN_BAN):
        return

    text = message.text.partition(" ")[2].strip()
    target, period, reason = None, -1, "не указана"

    if message.reply_to_message:
        target = resolve_user(message, "")
        parts = text.split(maxsplit=1)
        if parts:
            period = parse_period(parts[0])
            if len(parts) > 1:
                reason = parts[1]
    else:
        parts = text.split(maxsplit=2)
        if not parts:
            return bot.reply_to(message, "Формат: /ban @user [период] [причина]")
        target = resolve_user(message, parts[0])
        if len(parts) > 1:
            period = parse_period(parts[1])
        if len(parts) > 2:
            reason = parts[2]

    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")

    db.set_ban(target, message.from_user.id, reason, period)
    db.add_log("ban", message.from_user.id, target, f"{reason} / {format_until(period)}")
    period_str = format_until(period)

    bot.reply_to(message,
        f"🚫 <b>Пользователь заблокирован</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮 <b>Администратор:</b> {admin_pseudo(message.from_user.id)}\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>\n"
        f"⏳ <b>Срок:</b> {period_str}\n"
        f"📋 <b>Причина:</b> {reason}")

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📩 Обжаловать наказание", callback_data="appeal_start"))
    unban_date = "никогда" if period == -1 else time.strftime('%d.%m.%Y %H:%M', time.localtime(period))
    send_to_user(
        target,
        f"🚫 <b>Вы заблокированы в боте</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏳ <b>Срок:</b> {period_str}\n"
        f"📅 <b>Разблокировка:</b> {unban_date}\n"
        f"📋 <b>Причина:</b> {reason}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<i>Если не согласны — нажмите кнопку ниже.</i>",
        kb=kb)


@bot.message_handler(commands=["unban"])
def cmd_unban(message):
    if not check_access(message, Config.MIN_UNBAN):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    db.remove_ban(target)
    db.add_log("unban", message.from_user.id, target)
    bot.reply_to(message,
        f"✅ <b>Пользователь разблокирован</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮 <b>Администратор:</b> {admin_pseudo(message.from_user.id)}\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>")
    send_to_user(target,
        "🕊 <b>Вы были разблокированы</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "<i>Добро пожаловать обратно.</i>")


# ══════════════════════════════════════════════════════
# /warn /unwarn /clearwarns
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["warn"])
def cmd_warn(message):
    if not check_access(message, Config.MIN_WARN):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    u = db.get_user(target)
    warns = (u["warns"] or 0) + 1
    db.set_warns(target, warns)
    db.add_log("warn", message.from_user.id, target, f"{warns}/{Config.WARN_LIMIT}")
    bot.reply_to(message,
        f"⚠️ <b>Выдано предупреждение</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮 <b>Администратор:</b> {admin_pseudo(message.from_user.id)}\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>\n"
        f"📊 <b>Варны:</b> {warns} / {Config.WARN_LIMIT}")
    send_to_user(target,
        f"⚠️ <b>Вы получили предупреждение</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Варнов:</b> {warns} / {Config.WARN_LIMIT}")
    if warns >= Config.WARN_LIMIT:
        until = int(time.time()) + 86400
        db.set_ban(target, message.from_user.id, "3 варна", until)
        db.add_log("autoban", message.from_user.id, target, "3 warns")
        send_to_user(target,
            "⛓ <b>Вы забанены за 3 предупреждения</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⏳ <b>Срок:</b> 24 часа")
        bot.send_message(Config.SUPPORT_GROUP,
            f"⛓ <b>Автобан за 3 предупреждения</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
            f"🆔 <code>{target}</code>\n"
            f"⏳ <b>Срок:</b> 24 часа")


@bot.message_handler(commands=["unwarn"])
def cmd_unwarn(message):
    if not check_access(message, Config.MIN_UNWARN):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    u = db.get_user(target)
    warns = max(0, (u["warns"] or 0) - 1)
    db.set_warns(target, warns)
    db.add_log("unwarn", message.from_user.id, target, f"-> {warns}")
    bot.reply_to(message,
        f"✅ <b>Варн снят</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮 <b>Администратор:</b> {admin_pseudo(message.from_user.id)}\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>\n"
        f"📊 <b>Осталось:</b> {warns}")


@bot.message_handler(commands=["clearwarns"])
def cmd_clearwarns(message):
    if not check_access(message, Config.MIN_PBAN):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    db.set_warns(target, 0)
    db.add_log("clearwarns", message.from_user.id, target)
    bot.reply_to(message,
        f"✅ <b>Варны сброшены</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮 <b>Администратор:</b> {admin_pseudo(message.from_user.id)}\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>")


# ══════════════════════════════════════════════════════
# /kick /mute /unmute
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["kick"])
def cmd_kick(message):
    if not check_access(message, Config.MIN_SETROLE):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    db.delete_ticket(target)
    until = int(time.time()) + 3600
    db.set_ban(target, message.from_user.id, "Кик администратором", until)
    db.add_log("kick", message.from_user.id, target)
    bot.reply_to(message,
        f"👢 <b>Пользователь кикнут</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮 <b>Администратор:</b> {admin_pseudo(message.from_user.id)}\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>\n"
        f"⏳ <b>Срок:</b> 1 час")
    send_to_user(target,
        "👢 <b>Вас кикнули</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⏳ <b>Срок:</b> 1 час\n"
        "📋 <b>Причина:</b> Кик администратором")


@bot.message_handler(commands=["mute"])
def cmd_mute(message):
    if not check_access(message, Config.MIN_SETROLE):
        return
    text = message.text.partition(" ")[2].strip()
    parts = text.split()
    target = resolve_user(message, parts[0] if parts else "")
    if not target:
        return bot.reply_to(message, "Формат: /mute @user [7d]")
    period = parse_period(parts[1]) if len(parts) > 1 else int(time.time()) + 3600
    if period == -1:
        period = int(time.time()) + 3600
    db.set_muted(target, period)
    db.add_log("mute", message.from_user.id, target, format_until(period))
    bot.reply_to(message,
        f"🔇 <b>Пользователь замучен</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮 <b>Администратор:</b> {admin_pseudo(message.from_user.id)}\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>\n"
        f"⏳ <b>До:</b> {format_until(period)}")
    send_to_user(target,
        f"🔇 <b>Вы замучены</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏳ <b>До:</b> {format_until(period)}")


@bot.message_handler(commands=["unmute"])
def cmd_unmute(message):
    if not check_access(message, Config.MIN_SETROLE):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    db.set_muted(target, 0)
    db.add_log("unmute", message.from_user.id, target)
    bot.reply_to(message,
        f"🔊 <b>Мут снят</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮 <b>Администратор:</b> {admin_pseudo(message.from_user.id)}\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>")
    send_to_user(target,
        "🔊 <b>Мут снят</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "<i>Можете писать снова.</i>")


# ══════════════════════════════════════════════════════
# /dialogs /dialog /cleardialogs
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["dialogs"])
def cmd_dialogs(message):
    if not check_access(message, Config.MIN_SETROLE):
        return
    rows = db.get_all_tickets()
    if not rows:
        return bot.reply_to(message, "📭 Активных диалогов нет")
    text = (
        f"💬 <b>Активные диалоги</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Всего:</b> {len(rows)}\n\n"
    )
    for r in rows:
        text += (
            f"👤 <b>{nick_tg(r['user_id'])}</b>\n"
            f"   🆔 <code>{r['user_id']}</code>\n"
            f"   👮 Админ: {admin_pseudo(r['admin_id'])}\n\n"
        )
    bot.reply_to(message, text)


@bot.message_handler(commands=["dialog"])
def cmd_dialog(message):
    if not check_access(message, Config.MIN_SETROLE):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    admin_id = db.get_ticket(target)
    if not admin_id:
        return bot.reply_to(message, f"📭 У {nick_tg(target)} нет активного диалога")
    bot.reply_to(message,
        f"💬 <b>Диалог</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>\n"
        f"👮 <b>Администратор:</b> {admin_pseudo(admin_id)}")


@bot.message_handler(commands=["cleardialogs"])
def cmd_cleardialogs(message):
    if message.from_user.id != Config.DEVELOPER_ID:
        return bot.reply_to(message, "❌ Только разработчик")
    rows = db.get_all_tickets()
    count = len(rows)
    db.clear_tickets()
    db.add_log("cleardialogs", message.from_user.id, details=f"closed {count}")
    bot.reply_to(message, f"✅ Закрыто диалогов: <b>{count}</b>")


# ══════════════════════════════════════════════════════
# /pban /punban
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["pban"])
def cmd_pban(message):
    if not check_access(message, Config.MIN_PBAN):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    db.set_pban(target, True)
    db.add_log("pban", message.from_user.id, target)
    bot.reply_to(message,
        f"🚫 <b>Обжалование запрещено</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>")


@bot.message_handler(commands=["punban"])
def cmd_punban(message):
    if not check_access(message, Config.MIN_PUNBAN):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    db.set_pban(target, False)
    db.add_log("punban", message.from_user.id, target)
    bot.reply_to(message,
        f"✅ <b>Обжалование разрешено</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>")


# ══════════════════════════════════════════════════════
# /setwelcome
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["setwelcome"])
def cmd_setwelcome(message):
    if not check_access(message, Config.MIN_SETWELCOME):
        return
    text = message.text.partition(" ")[2].strip()
    if not text:
        return bot.reply_to(message, "Формат: /setwelcome <текст>")
    db.set_setting("welcome", text)
    db.add_log("setwelcome", message.from_user.id)
    bot.reply_to(message, "✅ Приветствие обновлено")


# ══════════════════════════════════════════════════════
# /note /notes /clearnotes
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["note"])
def cmd_note(message):
    if not check_access(message, Config.MIN_NOTE):
        return
    text = message.text.partition(" ")[2].strip()
    parts = text.split(maxsplit=1)
    target = resolve_user(message, parts[0] if parts else "")
    if not target or len(parts) < 2:
        return bot.reply_to(message, "Формат: /note @user <текст>")
    db.add_note(target, message.from_user.id, parts[1])
    db.add_log("note", message.from_user.id, target)
    bot.reply_to(message,
        f"📝 <b>Заметка добавлена</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Пользователь:</b> {nick_tg(target)}\n"
        f"🆔 <code>{target}</code>")


@bot.message_handler(commands=["notes"])
def cmd_notes(message):
    if not check_access(message, Config.MIN_NOTE):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    notes = db.get_notes(target)
    if not notes:
        return bot.reply_to(message, f"📭 Заметок для {nick_tg(target)} нет")
    text = f"📝 <b>Заметки о {nick_tg(target)}</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    for n in notes:
        text += f"🗓 <i>{n['date']}</i>\n{n['text']}\n\n"
    bot.reply_to(message, text)


@bot.message_handler(commands=["clearnotes"])
def cmd_clearnotes(message):
    if not check_access(message, Config.MIN_PBAN):
        return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target:
        return bot.reply_to(message, "❌ Пользователь не найден")
    db.clear_notes(target)
    db.add_log("clearnotes", message.from_user.id, target)
    bot.reply_to(message, f"🧹 Заметки о {nick_tg(target)} очищены")


# ══════════════════════════════════════════════════════
# /top
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["top"])
def cmd_top(message):
    if not check_access(message, Config.MIN_RANKS):
        return
    rows = db.get_top_users(10)
    if not rows:
        return bot.reply_to(message, "📭 Пусто")
    text = "🏆 <b>Топ-10 по сообщениям</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    for i, r in enumerate(rows, 1):
        text += f"<b>{i}.</b> {nick_tg(r['user_id'])} — {r['messages']} сообщ.\n"
    bot.reply_to(message, text)


# ══════════════════════════════════════════════════════
# /logs (8+)
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["logs"])
def cmd_logs(message):
    if rank_of(message.from_user.id) < Config.MIN_LOGS:
        return bot.reply_to(message, "❌ Недостаточно прав! (нужен ранг 8+)")
    parts = message.text.split()
    limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
    limit = min(limit, 50)
    rows = db.get_logs(limit)
    if not rows:
        return bot.reply_to(message, "📭 Логов нет")
    text = f"📋 <b>Последние {len(rows)} действий</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    for r in rows:
        text += (
            f"🗓 <i>{r['date']}</i>\n"
            f"⚙️ <b>{r['action']}</b>\n"
            f"👤 target: <code>{r['target_id']}</code>\n"
            f"📝 {r['details']}\n\n"
        )
    bot.reply_to(message, text)


# ══════════════════════════════════════════════════════
# /broadcast (8+)
# ══════════════════════════════════════════════════════
@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(message):
    if rank_of(message.from_user.id) < Config.MIN_BROADCAST:
        return bot.reply_to(message, "❌ Недостаточно прав! (нужен ранг 8+)")
    text = message.text.partition(" ")[2].strip()
    if not text:
        return bot.reply_to(message, "Формат: /broadcast <текст>")

    rows = db.get_all_users()
    total = len(rows)
    sent, failed = 0, 0
    status_msg = bot.reply_to(message, f"📢 Начинаю рассылку... 0/{total}")

    for i, r in enumerate(rows, 1):
        try:
            bot.send_message(
                r["user_id"],
                f"📢 <b>Рассылка</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{text}")
            sent += 1
        except Exception:
            failed += 1
        if i % 10 == 0:
            try:
                bot.edit_message_text(f"📢 Рассылка... {i}/{total}",
                    status_msg.chat.id, status_msg.message_id)
            except Exception:
                pass
        time.sleep(0.05)

    db.add_log("broadcast", message.from_user.id,
               details=f"sent {sent}/{total}, failed {failed}")
    try:
        bot.edit_message_text(
            f"✅ <b>Рассылка завершена</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📤 <b>Отправлено:</b> {sent}/{total}\n"
            f"❌ <b>Ошибок:</b> {failed}",
            status_msg.chat.id, status_msg.message_id)
    except Exception:
        bot.reply_to(message, f"✅ Отправлено: {sent}/{total}, ошибок: {failed}")


# ══════════════════════════════════════════════════════
# ОБЖАЛОВАНИЕ
# ══════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data == "appeal_start")
def cb_appeal_start(call):
    uid = call.from_user.id
    ban = db.get_ban(uid)
    if not ban:
        return bot.answer_callback_query(call.id, "Вы не забанены")
    if ban["pban"]:
        return bot.answer_callback_query(call.id, "Обжалование недоступно", show_alert=True)
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📩 Написать заявку", callback_data="appeal_begin"))
    bot.edit_message_text("Нажмите чтобы написать заявку",
        call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "appeal_begin")
def cb_appeal_begin(call):
    uid = call.from_user.id
    last = db.get_last_appeal_time(uid)
    if last and time.time() - last < Config.APPEAL_COOLDOWN:
        remain = int(Config.APPEAL_COOLDOWN - (time.time() - last))
        return bot.answer_callback_query(call.id,
            f"⏳ Повторно через {remain//3600}ч {(remain%3600)//60}м", show_alert=True)
    appeal_sessions[uid] = {"step": 0, "answers": []}
    bot.edit_message_text(APPEAL_QUESTIONS[0],
        call.message.chat.id, call.message.message_id)


@bot.message_handler(
    func=lambda m: m.chat.type == "private" and m.from_user.id in appeal_sessions,
    content_types=["text"])
def appeal_step(message):
    uid = message.from_user.id
    state = appeal_sessions[uid]
    state["answers"].append(message.text)
    state["step"] += 1

    if state["step"] < len(APPEAL_QUESTIONS):
        bot.send_message(uid, APPEAL_QUESTIONS[state["step"]])
    else:
        answers = state["answers"]
        del appeal_sessions[uid]
        appeal_id = db.add_appeal(uid, answers)
        db.add_log("appeal_created", uid, details=f"#{appeal_id}")
        bot.send_message(uid,
            "📩 <b>Ваше обжалование отправлено</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<i>Ожидайте рассмотрения владельцем.</i>")

        text = (
            f"📩 <b>Заявка на обжалование</b> #{appeal_id}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Пользователь:</b> {nick_tg(uid)}\n"
            f"🆔 <code>{uid}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"❓ <b>Почему вас забанили?</b>\n{answers[1]}\n\n"
            f"⚠️ <b>Что вы нарушили?</b>\n{answers[1]}\n\n"
            f"🔧 <b>Как вы это исправите?</b>\n{answers[2]}\n\n"
            f"💡 <b>Почему мы должны вас разбанить?</b>\n{answers[3]}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<i>Примите решение:</i>"
        )
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"ap_ok_{appeal_id}"),
            types.InlineKeyboardButton("❌ Отказать", callback_data=f"ap_no_{appeal_id}"),
        )
        try:
            sent = bot.send_message(Config.CLAIMS_GROUP, text, reply_markup=kb)
            db.set_appeal_msg(appeal_id, sent.message_id)
        except Exception as e:
            print(f"[appeal send] {e}")


@bot.callback_query_handler(func=lambda c: c.data.startswith("ap_ok_") or c.data.startswith("ap_no_"))
def cb_appeal_decide(call):
    if rank_of(call.from_user.id) < Config.MIN_APPEAL_DECIDE:
        return bot.answer_callback_query(call.id, "❌ Недостаточно прав!", show_alert=True)

    action, aid = call.data.split("_")[1], int(call.data.split("_")[2])
    row = db.get_appeal(aid)
    if not row or row["status"] != "pending":
        return bot.answer_callback_query(call.id, "Уже обработано")
    uid = row["user_id"]

    if action == "ok":
        db.update_appeal_status(aid, "approved")
        db.remove_ban(uid)
        db.add_log("appeal_approve", call.from_user.id, uid, f"#{aid}")
        bot.send_message(Config.CLAIMS_GROUP,
            f"✅ <b>Обжалование одобрено</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👮 <b>Администратор:</b> {admin_pseudo(call.from_user.id)}\n"
            f"👤 <b>Пользователь:</b> {nick_tg(uid)}\n"
            f"🆔 <code>{uid}</code>")
        send_to_user(uid,
            "✅ <b>Ваше обжалование одобрено</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<i>Вы были разблокированы.</i>")
    else:
        db.update_appeal_status(aid, "rejected")
        db.add_log("appeal_reject", call.from_user.id, uid, f"#{aid}")
        bot.send_message(Config.CLAIMS_GROUP,
            f"❌ <b>Обжалование отклонено</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👮 <b>Администратор:</b> {admin_pseudo(call.from_user.id)}\n"
            f"👤 <b>Пользователь:</b> {nick_tg(uid)}\n"
            f"🆔 <code>{uid}</code>")
        send_to_user(uid,
            "❌ <b>Ваше обжалование отклонено</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<i>Решение окончательное.</i>")

    try:
        bot.edit_message_reply_markup(Config.CLAIMS_GROUP, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    bot.answer_callback_query(call.id)


# ══════════════════════════════════════════════════════
# LIVE-ДИАЛОГ
# ══════════════════════════════════════════════════════
@bot.message_handler(content_types=[
    "text", "photo", "video", "animation", "voice", "sticker",
    "video_note", "document", "audio"
])
def handle_messages(message):
    chat = message.chat.id
    uid = message.from_user.id

    if chat == Config.COMMANDS_GROUP:
        return

    # Группа поддержки: reply ТОЛЬКО на сообщение бота → юзеру
    if chat == Config.SUPPORT_GROUP and message.reply_to_message:
        rt = message.reply_to_message
        if rt.from_user.id != bot.get_me().id:
            return
        target_user = db.get_reply_user(rt.message_id)
        if not target_user:
            return
        if rank_of(uid) < Config.MIN_ANSWER:
            return bot.reply_to(message, "❌ Недостаточно прав!")

        try:
            bot.send_message(target_user,
                "📩 <b>Новое сообщение</b>\n"
                "<i>От администратора</i>")
            bot.copy_message(target_user, chat, message.message_id)
        except Exception as e:
            err = str(e)
            if "403" in err or "Forbidden" in err or "can't initiate" in err:
                bot.reply_to(message,
                    "⚠️ <b>Не удалось доставить сообщение</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "Пользователь ещё <b>не нажал /start</b> в боте "
                    "или заблокировал бота.\n\n"
                    "<i>Попросите его написать боту /start.</i>")
            else:
                bot.reply_to(message, f"❌ Не удалось отправить: {e}")
        return

    # ЛС
    if message.chat.type == "private":
        if uid in appeal_sessions:
            return

        ban = db.get_ban(uid)
        if ban:
            return

        if is_flood(uid):
            try:
                bot.reply_to(message, f"⏳ Не так быстро! Мут {Config.MUTE_TIME} сек.")
            except Exception:
                pass
            return

        if message.from_user.username:
            db.set_username(uid, message.from_user.username)
        db.inc_messages(uid)

        admin_id = db.get_ticket(uid)

        # Нет активного диалога → предлагаем вызвать админа
        if not admin_id:
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton(
                "📞 Позвать администратора", callback_data="call_admin"))
            try:
                bot.send_message(uid,
                    "⚠️ <b>У вас ещё нет активного диалога</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "Нажмите кнопку ниже, чтобы вызвать администратора.",
                    reply_markup=kb)
            except Exception:
                pass
            return

        # Есть тикет — пересылаем
        try:
            header = bot.send_message(
                Config.SUPPORT_GROUP,
                f"📩 <b>Новое сообщение от пользователя</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 {nick_tg(uid)} | <code>{uid}</code>\n"
                f"👮 <b>Администратор:</b> {admin_pseudo(admin_id)}")
            bot.copy_message(Config.SUPPORT_GROUP, chat, message.message_id)
            db.save_reply(header.message_id, uid)

            kb_admin = types.InlineKeyboardMarkup()
            kb_admin.add(types.InlineKeyboardButton(
                "🔚 Закрыть диалог", callback_data=f"close_{uid}"))
            bot.send_message(admin_id,
                f"📩 <b>Новое сообщение от пользователя</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 {nick_tg(uid)} | <code>{uid}</code>")
            bot.copy_message(admin_id, chat, message.message_id)
            try:
                bot.send_message(admin_id, "👇 Управление:", reply_markup=kb_admin)
            except Exception:
                pass

            kb_user = types.InlineKeyboardMarkup()
            kb_user.add(types.InlineKeyboardButton(
                "🔚 Закрыть диалог", callback_data="user_close"))
            try:
                bot.send_message(uid, "👇 Управление диалогом:", reply_markup=kb_user)
            except Exception:
                pass
        except Exception as e:
            print(f"[forward] {e}")


# ══════════════════════════════════════════════════════
# ЗАПУСК
# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🤖 Бот запущен...")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)