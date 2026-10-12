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
    """Псевдоним админа в формате (#ник)."""
    nick = db.get_user(uid)["nickname"]
    if nick:
        return f"(#{nick})"
    return "(#Администратор)"


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
        text += "/note @user [текст] / /notes @user\n\n"

    if r >= Config.MIN_PBAN:
        text += "<b>👑 Ранг 8+:</b>\n"
        text += "/unban @user\n"
        text += "/pban / /punban @user\n"
        text += "/setwelcome [текст]\n"
        text += "/setrules [текст]\n"
        text += "/setinfo [текст]\n"
        text += "/setgwelcome [текст]\n"
        text += "/clearwarns @user\n"
        text += "/broadcast [текст]\n"
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
        return bot.reply_to(message, "Формат: /setrules [текст]")
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
        return bot.reply_to(message, "Формат: /setinfo [текст]")
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
            "Формат: /setgwelcome [текст]\n"
            "Используйте {name} для подстановки имени.\n\n"
            "Пример:\n"
            "/setgwelcome 🖤 Добро пожаловать, {name}!")
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
        target = db.get_reply_user(rt.message_id)
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
            "Если снова понадобится помощь — нажмите /start")
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
            "Если снова понадобится помощь — нажмите /start")
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
            f"Если не согласны — нажмите кнопку ниже."
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
        "Ожидайте.",
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
        f"✅ <b>Администратор принял вас</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👮 <b>Ваш администратор:</b> {admin_pseudo(admin_uid)}\n"
        f"💬 Пишите сообщения — они уйдут администратору анонимно.\n\n"
        f"Нажмите кнопку ниже, чтобы завершить диалог.",
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
        bot.edit_message_reply_markup(