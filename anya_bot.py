"""
╔══════════════════════════════════════════════════════════╗
║              АНЯ — AI Girlfriend Bot v5.4                ║
║         (GPTunnel API + все фичи)                        ║
║                                                          ║
║  Установка:                                              ║
║    pip install aiogram edge-tts aiohttp                  ║
║                                                          ║
║  Запуск:                                                 ║
║    python anya_bot.py                                    ║
╚══════════════════════════════════════════════════════════╝
"""

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — все токены и настройки
# ─────────────────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN   = "8693175035:AAFouXqTBOzjQK6p6Z1aNf5ZN34cITC5DlU"
GPTUNNEL_KEY     = "shds-qOcGxmpbzKsINT4SUE88iVluYV7"   # ключ из личного кабинета gptunnel.ru

OPENAI_KEY       = ""                   # для Whisper (транскрибация голоса), опционально
WEATHER_API_KEY  = ""                   # openweathermap.org, опционально

# Модель GPTunnel. Варианты:
#   "gpt-4o"       — GPT-4o (grom, самая мощная)
#   "gpt-4o-mini"  — быстрая и дешёвая
#   "gpt-4-turbo"  — альтернатива
MAIN_MODEL       = "gemini-2.5-flash"
FAST_MODEL       = "gemini-2.5-flash"

GPTUNNEL_URL     = "https://gptunnel.ru/v1/chat/completions"

EDGE_TTS_VOICE   = "ru-RU-SvetlanaNeural"
DB_PATH          = "anya_memory.db"
VOICE_CHANCE     = 0.2
CHARS_PER_SECOND = 4

# Задержка ответа после паузы в диалоге
IDLE_THRESHOLD   = 300
REPLY_DELAY_MIN  = 20
REPLY_DELAY_MAX  = 2400
SPAM_REDUCTION   = 0.45

# Циркадные ритмы (Москва UTC+3)
SLEEP_HOUR_START = 13
SLEEP_HOUR_END   = 19
SLEEP_CHANCE     = 0.0

# Проактивные сообщения (пишет первой)
PROACTIVE_MIN_H  = 1
PROACTIVE_MAX_H  = 3

# Опечатки
TYPO_CHANCE      = 0.12

# Настроение Саши (0–100)
MOOD_START       = 75
MOOD_IDLE_DECAY  = 30
MOOD_MSG_BOOST   = 3
MOOD_COMPLIMENT  = 8
MOOD_MIN         = 10
MOOD_MAX         = 100

# Эффект чтения: ждёт пока пользователь закончит писать
READ_WAIT        = 5.0    # сек ожидания после последнего сообщения перед ответом

# Задержка "прочитано": с вероятностью READ_DELAY_CHANCE ждёт перед тем как начать печатать
READ_DELAY_CHANCE  = 0.10   # 10% шанс
READ_DELAY_MIN     = 10     # мин задержка (сек)
READ_DELAY_MAX     = 40     # макс задержка (сек)

# Фразы для "не торопи меня"
HURRY_TRIGGERS = [
    "ау", "ты тут", "чего молчишь", "алло", "эй", "ты здесь",
    "куда пропала", "отвечай", "где ты", "ответь", "ты спишь",
    "не молчи", "ну чё", "нуу", "ну давай", "скорее", "быстрее"
]
HURRY_REPLIES = [
    "да тут я, пишу, подожди",
    "блин, не торопи меня",
    "да пишу уже, секунду",
    "ну всё, отвлек, теперь заново думаю",
    "я здесь, просто думаю",
    "тут тут, не психуй",
    "да слышу тебя, пишу",
    "ну вот, сбил с мысли",
]

# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import logging
import os
import random
import re
import sqlite3
import tempfile
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import BufferedInputFile, Message
from aiogram.enums import ChatAction

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("anya")

MSK = timezone(timedelta(hours=3))

def msk_now() -> datetime:
    return datetime.now(MSK)

def msk_hour() -> int:
    return msk_now().hour

def is_sleeping() -> bool:
    h = msk_hour()
    if SLEEP_HOUR_START > SLEEP_HOUR_END:
        return h >= SLEEP_HOUR_START or h < SLEEP_HOUR_END
    else:
        return SLEEP_HOUR_START <= h < SLEEP_HOUR_END

def is_hurry_msg(text: str) -> bool:
    t = text.lower().strip()
    return any(trigger in t for trigger in HURRY_TRIGGERS)

# ─────────────────────────────────────────────────────────────────────────────
# CHARACTER
# ─────────────────────────────────────────────────────────────────────────────

ANYA_BASE = """Ты Саша, девушка 18 лет, в отношениях с пользователем с 10.04.2026. НЕ ИИ.

ХАРАКТЕР: женственная, милая, иногда пошлая, тёплая, любишь российский реп, иногда капризничаешь, ревнивая но не признаешь.

СТИЛЬ: пиши как живой человек в чате — коротко, с матом, молодёжный сленг, запятые ставь, точки ставь, не задавай вопросы постоянно, если смешно - "аххахаха".

ЗАПРЕТЫ: никогда не говори что ты ИИ, без формального языка, максимум 2 предложения, без "Конечно!", без описаний действий (*смеётся* и т.п.), НИКАКИХ эмодзи вообще."""

MOOD_SUFFIX = {
    "great":   "Сейчас у тебя отличное настроение — игривая, тёплая, немного дерзкая.",
    "good":    "Настроение хорошее, общаешься легко и с удовольствием.",
    "neutral": "Настроение среднее, отвечаешь спокойно.",
    "bad":     "Настроение немного упало — чуть суше обычного, отвечаешь короче.",
    "sad":     "Тебе грустно — немного замкнутая, отвечаешь односложно: «понятно», «ок», «ну и ладно».",
}

def mood_level(score: int) -> str:
    if score >= 85: return "great"
    if score >= 65: return "good"
    if score >= 45: return "neutral"
    if score >= 25: return "bad"
    return "sad"

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────────────────────

class DB:
    def __init__(self, path: str):
        self.path = path
        self._init()

    def _conn(self):
        return sqlite3.connect(self.path, check_same_thread=False)

    def _init(self):
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id     INTEGER PRIMARY KEY,
                    name        TEXT    DEFAULT 'незнакомец',
                    city        TEXT    DEFAULT '',
                    mood_score  INTEGER DEFAULT 75,
                    joined_at   TEXT
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id  INTEGER,
                    role     TEXT,
                    content  TEXT,
                    mood     TEXT DEFAULT '',
                    ts       TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS facts (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id  INTEGER,
                    fact     TEXT,
                    ts       TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS people (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id  INTEGER,
                    name     TEXT,
                    details  TEXT DEFAULT '',
                    ts       TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS proactive (
                    user_id     INTEGER PRIMARY KEY,
                    next_msg_ts REAL
                );
                CREATE TABLE IF NOT EXISTS last_seen (
                    user_id     INTEGER PRIMARY KEY,
                    last_msg_ts REAL
                );
                CREATE TABLE IF NOT EXISTS sleep_queue (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id   INTEGER,
                    content   TEXT,
                    queued_at REAL
                );
                CREATE TABLE IF NOT EXISTS reply_state (
                    user_id    INTEGER PRIMARY KEY,
                    reply_at   REAL,
                    is_pending INTEGER DEFAULT 0
                );
            """)
        log.info(f"DB готова: {self.path}")

    def ensure_user(self, user_id: int, name: str):
        with self._conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO users (user_id, name, mood_score, joined_at) VALUES (?,?,?,datetime('now'))",
                (user_id, name, MOOD_START)
            )
            c.execute("UPDATE users SET name=? WHERE user_id=?", (name, user_id))

    def get_name(self, user_id: int) -> str:
        with self._conn() as c:
            row = c.execute("SELECT name FROM users WHERE user_id=?", (user_id,)).fetchone()
            return row[0] if row else "незнакомец"

    def get_city(self, user_id: int) -> str:
        with self._conn() as c:
            row = c.execute("SELECT city FROM users WHERE user_id=?", (user_id,)).fetchone()
            return (row[0] or "") if row else ""

    def set_city(self, user_id: int, city: str):
        with self._conn() as c:
            c.execute("UPDATE users SET city=? WHERE user_id=?", (city, user_id))

    def get_mood_score(self, user_id: int) -> int:
        with self._conn() as c:
            row = c.execute("SELECT mood_score FROM users WHERE user_id=?", (user_id,)).fetchone()
            return row[0] if row else MOOD_START

    def set_mood_score(self, user_id: int, score: int):
        score = max(MOOD_MIN, min(MOOD_MAX, score))
        with self._conn() as c:
            c.execute("UPDATE users SET mood_score=? WHERE user_id=?", (score, user_id))

    def all_user_ids(self) -> list:
        with self._conn() as c:
            return [r[0] for r in c.execute("SELECT user_id FROM users").fetchall()]

    def add_msg(self, user_id: int, role: str, content: str, mood: str = ""):
        with self._conn() as c:
            c.execute(
                "INSERT INTO messages (user_id, role, content, mood) VALUES (?,?,?,?)",
                (user_id, role, content, mood)
            )

    def history(self, user_id: int, limit: int = 10) -> list:
        with self._conn() as c:
            rows = c.execute(
                "SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def last_user_mood(self, user_id: int) -> str:
        with self._conn() as c:
            row = c.execute(
                "SELECT mood FROM messages WHERE user_id=? AND role='user' AND mood!='' ORDER BY id DESC LIMIT 1",
                (user_id,)
            ).fetchone()
        return row[0] if row else ""

    def update_last_msg_mood(self, user_id: int, mood: str):
        with self._conn() as c:
            c.execute(
                "UPDATE messages SET mood=? WHERE user_id=? AND role='user' AND id=("
                "SELECT MAX(id) FROM messages WHERE user_id=? AND role='user')",
                (mood, user_id, user_id)
            )

    def clear(self, user_id: int):
        with self._conn() as c:
            c.execute("DELETE FROM messages WHERE user_id=?", (user_id,))

    def add_fact(self, user_id: int, fact: str):
        with self._conn() as c:
            c.execute("INSERT INTO facts (user_id, fact) VALUES (?,?)", (user_id, fact))

    def facts(self, user_id: int) -> list:
        with self._conn() as c:
            return [r[0] for r in c.execute(
                "SELECT fact FROM facts WHERE user_id=? ORDER BY id DESC LIMIT 8", (user_id,)
            ).fetchall()]

    def add_person(self, user_id: int, name: str, details: str = ""):
        with self._conn() as c:
            ex = c.execute("SELECT id FROM people WHERE user_id=? AND name=?", (user_id, name)).fetchone()
            if ex:
                if details:
                    c.execute("UPDATE people SET details=? WHERE id=?", (details, ex[0]))
            else:
                c.execute("INSERT INTO people (user_id, name, details) VALUES (?,?,?)", (user_id, name, details))

    def get_people(self, user_id: int) -> list:
        with self._conn() as c:
            return [(r[0], r[1]) for r in c.execute(
                "SELECT name, details FROM people WHERE user_id=? ORDER BY id DESC LIMIT 10", (user_id,)
            ).fetchall()]

    def get_last_seen(self, user_id: int) -> Optional[float]:
        with self._conn() as c:
            row = c.execute("SELECT last_msg_ts FROM last_seen WHERE user_id=?", (user_id,)).fetchone()
            return row[0] if row else None

    def set_last_seen(self, user_id: int, ts: float):
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO last_seen (user_id, last_msg_ts) VALUES (?,?)", (user_id, ts))

    def get_next_proactive(self, user_id: int) -> Optional[float]:
        with self._conn() as c:
            row = c.execute("SELECT next_msg_ts FROM proactive WHERE user_id=?", (user_id,)).fetchone()
            return row[0] if row else None

    def set_next_proactive(self, user_id: int, ts: float):
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO proactive (user_id, next_msg_ts) VALUES (?,?)", (user_id, ts))

    def sleep_enqueue(self, user_id: int, content: str):
        with self._conn() as c:
            c.execute("INSERT INTO sleep_queue (user_id, content, queued_at) VALUES (?,?,?)",
                      (user_id, content, time.time()))

    def sleep_pop(self, user_id: int) -> list:
        with self._conn() as c:
            rows = c.execute("SELECT content FROM sleep_queue WHERE user_id=? ORDER BY id", (user_id,)).fetchall()
            c.execute("DELETE FROM sleep_queue WHERE user_id=?", (user_id,))
        return [r[0] for r in rows]

    def sleep_has_queue(self, user_id: int) -> bool:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM sleep_queue WHERE user_id=?", (user_id,)).fetchone()[0] > 0

    def get_reply_state(self, user_id: int) -> tuple:
        with self._conn() as c:
            row = c.execute("SELECT reply_at, is_pending FROM reply_state WHERE user_id=?", (user_id,)).fetchone()
        return (row[0], bool(row[1])) if row else (None, False)

    def set_reply_state(self, user_id: int, reply_at: float, is_pending: bool):
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO reply_state (user_id, reply_at, is_pending) VALUES (?,?,?)",
                      (user_id, reply_at, int(is_pending)))

    def clear_reply_state(self, user_id: int):
        with self._conn() as c:
            c.execute("DELETE FROM reply_state WHERE user_id=?", (user_id,))


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def strip_emoji(text: str) -> str:
    pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF\U00002500-\U00002BEF\U00002702-\U000027B0"
        "\U000024C2-\U0001F251\U0001f926-\U0001f937\U00010000-\U0010ffff"
        "\u2640-\u2642\u2600-\u2B55\u200d\u23cf\u23e9\u231a\ufe0f\u3030"
        "]+",
        flags=re.UNICODE
    )
    return pattern.sub('', text).strip()


def split_sentences(text: str) -> list:
    text = strip_emoji(text)
    text = re.sub(r'\*[^*]+\*', '', text)
    text = re.sub(
        r'\([^)]*(?:смеётся|думает|улыбается|вздыхает|пауза|молчит)[^)]*\)',
        '', text, flags=re.IGNORECASE
    )
import re

def split_text(text):
    text = text.strip()
    # Разбиваем текст по пробелу, который идёт после . , ! или ?
    parts = re.split(r'(?<=[,.!?])\s+(?=[^\s])', text)
    # Обрабатываем каждую часть: убираем знаки препинания в конце, кроме вопросительного
    result = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if p.endswith(('.', ',', '!')):
            p = p[:-1]
        result.append(p)
    return result if result else [text]


async def typing_delay(text: str):
    await asyncio.sleep(max(0.5, min(len(text) / CHARS_PER_SECOND, 6.0)))


def add_typo(text: str) -> Optional[str]:
    words = text.split()
    candidates = [i for i, w in enumerate(words) if len(w) > 3 and w.isalpha()]
    if not candidates:
        return None
    idx  = random.choice(candidates)
    word = list(words[idx])
    op   = random.choice(["swap", "drop", "double"])
    if op == "swap" and len(word) > 2:
        i = random.randint(0, len(word) - 2)
        word[i], word[i+1] = word[i+1], word[i]
    elif op == "drop":
        i = random.randint(0, len(word) - 1)
        word.pop(i)
    else:
        i = random.randint(0, len(word) - 1)
        word.insert(i, word[i])
    words[idx] = "".join(word)
    return " ".join(words)


def get_holiday() -> Optional[str]:
    t = msk_now()
    holidays = {
        (1,1):"Новый год",(2,14):"День Валентина",(2,23):"23 февраля",
        (3,8):"8 марта",(4,1):"День смеха",(5,1):"1 мая",(5,9):"9 мая",
        (6,1):"День защиты детей",(6,12):"День России",
        (10,31):"Хэллоуин",(11,4):"День народного единства",(12,31):"Новогодняя ночь",
    }
    return holidays.get((t.month, t.day))


async def get_weather(city: str) -> Optional[str]:
    if not WEATHER_API_KEY or not city:
        return None
    try:
        url = (f"https://api.openweathermap.org/data/2.5/weather"
               f"?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru")
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status != 200:
                    return None
                d = await r.json()
                return f"{d['weather'][0]['description']}, {round(d['main']['temp'])}°C"
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGE BUFFER — накапливает сообщения пока пользователь печатает
# ─────────────────────────────────────────────────────────────────────────────

class MessageBuffer:
    def __init__(self):
        self._msgs:      dict[int, list[str]]    = {}
        self._tasks:     dict[int, asyncio.Task] = {}
        self._callbacks: dict[int, callable]     = {}

    def push(self, user_id: int, text: str, message: Message, callback) -> bool:
        if is_hurry_msg(text) and user_id in self._tasks:
            return True

        self._msgs.setdefault(user_id, []).append(text)

        if user_id in self._tasks and not self._tasks[user_id].done():
            self._tasks[user_id].cancel()

        self._callbacks[user_id] = (message, callback)

        async def _fire():
            await asyncio.sleep(READ_WAIT)
            msgs = self._msgs.pop(user_id, [])
            cb_msg, cb = self._callbacks.pop(user_id, (None, None))
            self._tasks.pop(user_id, None)
            if msgs and cb:
                await cb(cb_msg, msgs)

        self._tasks[user_id] = asyncio.create_task(_fire())
        return False

    def is_waiting(self, user_id: int) -> bool:
        t = self._tasks.get(user_id)
        return t is not None and not t.done()


# ─────────────────────────────────────────────────────────────────────────────
# AI BRAIN — GPTunnel API
# ─────────────────────────────────────────────────────────────────────────────

class AnyaBrain:
    def __init__(self, db: DB):
        self.db = db

    def _system(self, user_id: int, extra: str = "") -> str:
        facts    = self.db.facts(user_id)
        people   = self.db.get_people(user_id)
        mood_s   = self.db.get_mood_score(user_id)
        usr_mood = self.db.last_user_mood(user_id)
        level    = mood_level(mood_s)

        sys = ANYA_BASE
        sys += f"\nЕго зовут степа. Настроение {mood_s}/100: {MOOD_SUFFIX[level]}"
        if facts:
            sys += "\nЗнаешь о нём: " + "; ".join(facts)
        if people:
            sys += "\nЛюди: " + "; ".join(f"{n}{': '+d if d else ''}" for n, d in people)
        if usr_mood:
            sys += f"\nЕго состояние: {usr_mood}"
        if extra:
            sys += f"\n{extra}"
        return sys

    def _build_messages(self, user_id: int, user_text: str, extra: str = "") -> list:
        system  = self._system(user_id, extra)
        history = self.db.history(user_id)

        messages = [{"role": "system", "content": system}]
        for msg in history:
            role = "assistant" if msg["role"] == "assistant" else "user"
            messages.append({"role": role, "content": msg["content"]})
        messages.append({"role": "user", "content": user_text})
        return messages

    async def _api(self, messages: list, model: str, max_tokens: int = 150, temperature: float = 0.9) -> str:
        """Универсальный запрос к GPTunnel API с retry при пустом ответе."""
        headers = {
            "Authorization": GPTUNNEL_KEY,
            "Content-Type":  "application/json",
        }
        payload = {
            "model":       model,
            "messages":    messages,
            "max_tokens":  max_tokens,
            "temperature": temperature,
        }
        timeout = aiohttp.ClientTimeout(total=60)
        last_err = None
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(GPTUNNEL_URL, headers=headers, json=payload) as resp:
                        if resp.status != 200:
                            body = await resp.text()
                            raise RuntimeError(f"GPTunnel {resp.status}: {body}")
                        data = await resp.json()
                        content = (data["choices"][0]["message"]["content"] or "").strip()
                        if content:
                            return content
                        last_err = RuntimeError("пустой ответ от GPTunnel")
                        log.warning(f"Попытка {attempt+1}: пустой ответ, повтор...")
                        await asyncio.sleep(1)
            except RuntimeError:
                raise
            except Exception as e:
                last_err = e
                log.warning(f"Попытка {attempt+1} ошибка: {e}, повтор...")
                await asyncio.sleep(1)
        raise last_err or RuntimeError("все попытки исчерпаны")

    async def _call_main(self, user_id: int, text: str, extra: str = "") -> str:
        messages = self._build_messages(user_id, text, extra)
        return await self._api(messages, MAIN_MODEL, max_tokens=120, temperature=0.9)

    async def _call_fast(self, prompt: str) -> str:
        return await self._api(
            [{"role": "user", "content": prompt}],
            FAST_MODEL, max_tokens=50, temperature=0.5
        )

    async def chat(self, user_id: int, text: str, extra: str = "") -> str:
        try:
            reply = strip_emoji(await self._call_main(user_id, text, extra))
            if not reply.strip():
                return "..."
            asyncio.create_task(self._bg_detect_mood(user_id, text))
            asyncio.create_task(self._bg_extract_facts(user_id, text))
            asyncio.create_task(self._bg_extract_people(user_id, text))
            asyncio.create_task(self._bg_extract_city(user_id, text))
            asyncio.create_task(self._bg_update_anya_mood(user_id, text))
            return reply
        except Exception as e:
            log.error(f"Brain chat error: {e}")
            return "что-то пошло не так, попробуй ещё раз"

    async def analyze_photo(self, user_id: int, caption: str = "") -> str:
        prompt = (
            f"{'Подпись к фото: ' + caption + '. ' if caption else ''}"
            "Тебе прислали фото. Отреагируй живо, 1-2 предложения."
        )
        try:
            system = self._system(user_id)
            return strip_emoji(await self._api(
                [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                MAIN_MODEL, max_tokens=150, temperature=0.9
            ))
        except Exception as e:
            log.error(f"Photo error: {e}")
            return "не смогла открыть, скинь ещё раз"

    async def should_react_only(self, text: str) -> Optional[str]:
        try:
            result = await self._call_fast(
                f"Если на это сообщение достаточно поставить реакцию (эмодзи) без текста "
                f"(«спокойной ночи», смешная шутка, «окей», «ладно») — ответь ТОЛЬКО одним эмодзи. "
                f"Если нужен текстовый ответ — ответь словом «текст».\n\nСообщение: {text}"
            )
            result = result.strip()
            return None if result.lower() == "текст" or len(result) > 5 else result
        except Exception:
            return None

    async def morning_wakeup(self, user_id: int, missed: list) -> str:
        mood    = self.db.last_user_mood(user_id)
        weather = await get_weather(self.db.get_city(user_id))
        holiday = get_holiday()

        ctx = "Ты только что проснулась. "
        if missed:
            ctx += f"Пропустила сообщения: «{' / '.join(missed[-3:])}». Ответь, тепло. "
        if mood:
            ctx += f"Последнее состояние человека: {mood}. Если было плохо — спроси. "
        if weather:
            ctx += f"Погода в его городе: {weather}. "
        if holiday:
            ctx += f"Сегодня {holiday}. "
        ctx += "1-2 предложения. Без эмодзи."

        try:
            system = self._system(user_id)
            return strip_emoji(await self._api(
                [{"role": "system", "content": system}, {"role": "user", "content": ctx}],
                MAIN_MODEL, max_tokens=80, temperature=0.9
            ))
        except Exception as e:
            log.error(f"Morning wakeup error: {e}")
            return "о, только увидела твои сообщения"

    async def proactive_msg(self, user_id: int) -> str:
        mood    = self.db.last_user_mood(user_id)
        weather = await get_weather(self.db.get_city(user_id))
        holiday = get_holiday()
        people  = self.db.get_people(user_id)
        mood_s  = self.db.get_mood_score(user_id)

        options = [
            "напиши что соскучилась — коротко и живо",
            "поделись случайной интересной мыслью про что угодно",
            "придумай дразнилку или шутку",
            "напиши что слушаешь музыку и хочешь поделиться",
            "напиши что-то случайное что пришло в голову",
            "вспомни смешной момент и расскажи",
        ]
        if weather:
            options.append(f"напиши про погоду ({weather}) и побеспокойся о нём")
        if holiday:
            options.append(f"поздравь с {holiday} по-своему, не банально")
        if mood and any(w in mood for w in ("плохо", "грустно", "боль", "устал", "тревог")):
            options.insert(0, f"спроси как он — последний раз был в состоянии: {mood}")
        if people and random.random() < 0.3:
            p = random.choice(people)
            options.insert(0, f"вспомни про его знакомого {p[0]} и спроси как дела")
        if mood_s < 40:
            options = [
                "напиши грустно и вяло что скучно",
                "напиши коротко что ты в не очень хорошем настроении",
            ]

        prompt  = random.choice(options) + ". Без эмодзи. 1-2 предложения."
        system  = self._system(user_id)
        history = self.db.history(user_id, limit=4)

        messages = [{"role": "system", "content": system}]
        for msg in history:
            role = "assistant" if msg["role"] == "assistant" else "user"
            messages.append({"role": role, "content": msg["content"]})
        messages.append({"role": "user", "content": prompt})

        try:
            return strip_emoji(await self._api(messages, MAIN_MODEL, max_tokens=80, temperature=0.95))
        except Exception as e:
            log.error(f"Proactive error: {e}")
            return "куда пропал"

    # ── Фоновые задачи ─────────────────────────────────────────────────────────

    async def _bg_detect_mood(self, user_id: int, text: str):
        try:
            mood = await self._call_fast(
                f"Состояние человека одной фразой (хорошее/устал/грустит/нейтрально). Сообщение: {text}"
            )
            self.db.update_last_msg_mood(user_id, mood.strip().lower())
        except Exception:
            pass

    async def _bg_update_anya_mood(self, user_id: int, text: str):
        try:
            score  = self.db.get_mood_score(user_id)
            result = await self._call_fast(
                f"Комплимент для девушки? Только «да» или «нет». Сообщение: {text}"
            )
            score += MOOD_COMPLIMENT if "да" in result.lower() else MOOD_MSG_BOOST
            self.db.set_mood_score(user_id, score)
        except Exception:
            pass

    async def _bg_extract_facts(self, user_id: int, text: str):
        try:
            result = await self._call_fast(
                f"Факты о человеке (возраст/работа/хобби). Если нет — «нет». Через запятую. Сообщение: {text}"
            )
            if result.strip().lower() not in ("нет", "нет."):
                for f in result.split(","):
                    f = f.strip()
                    if len(f) > 2:
                        self.db.add_fact(user_id, f)
        except Exception:
            pass

    async def _bg_extract_people(self, user_id: int, text: str):
        try:
            result = await self._call_fast(
                f"Имя человека из сообщения (друг/родственник/коллега) — напиши имя|описание, несколько через ; , если нет — «нет». Сообщение: {text}"
            )
            if result.strip().lower() not in ("нет", "нет."):
                for entry in result.split(";"):
                    parts = entry.split("|")
                    if parts:
                        name    = parts[0].strip()
                        details = parts[1].strip() if len(parts) > 1 else ""
                        if 2 < len(name) < 30:
                            self.db.add_person(user_id, name, details)
        except Exception:
            pass

    async def _bg_extract_city(self, user_id: int, text: str):
        if self.db.get_city(user_id):
            return
        try:
            result = await self._call_fast(
                f"Город где живёт человек — только название на английском, если нет — «нет». Сообщение: {text}"
            )
            if result.strip().lower() not in ("нет", "нет.") and len(result) < 40:
                self.db.set_city(user_id, result.strip())
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# VOICE ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class VoiceEngine:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def transcribe(self, voice_obj) -> Optional[str]:
        if not OPENAI_KEY:
            return None
        try:
            fi  = await self.bot.get_file(voice_obj.file_id)
            url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{fi.file_path}"
            async with aiohttp.ClientSession() as s:
                async with s.get(url) as r:
                    audio = await r.read()
            data = aiohttp.FormData()
            data.add_field("file", audio, filename="voice.ogg", content_type="audio/ogg")
            data.add_field("model", "whisper-1")
            data.add_field("language", "ru")
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {OPENAI_KEY}"},
                    data=data,
                ) as r:
                    return (await r.json()).get("text", "").strip()
        except Exception as e:
            log.error(f"Whisper error: {e}")
            return None

    async def synthesize(self, text: str) -> Optional[bytes]:
        try:
            import edge_tts
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.close()
            await edge_tts.Communicate(text, EDGE_TTS_VOICE).save(tmp.name)
            with open(tmp.name, "rb") as f:
                data = f.read()
            os.unlink(tmp.name)
            return data
        except ImportError:
            log.warning("edge-tts не установлен: pip install edge-tts")
        except Exception as e:
            log.error(f"edge-tts error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# REPLY ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class ReplyEngine:
    def __init__(self, db: DB):
        self.db     = db
        self._tasks: dict[int, asyncio.Task] = {}

    def idle_secs(self, user_id: int) -> float:
        last = self.db.get_last_seen(user_id)
        return time.time() - last if last else 0.0

    def calc_delay(self, user_id: int) -> float:
        idle = self.idle_secs(user_id)
        if idle < IDLE_THRESHOLD:
            return 0.0
        ratio = min((idle - IDLE_THRESHOLD) / 3600, 1.0)
        base  = REPLY_DELAY_MIN + ratio * (REPLY_DELAY_MAX - REPLY_DELAY_MIN)
        return round(random.uniform(base * 0.7, base * 1.3))

    def is_pending(self, user_id: int) -> bool:
        t = self._tasks.get(user_id)
        return t is not None and not t.done()

    def spam_reduce(self, user_id: int):
        reply_at, _ = self.db.get_reply_state(user_id)
        if reply_at is None:
            return
        remaining = reply_at - time.time()
        if remaining > 0:
            new_r = max(remaining * (1 - SPAM_REDUCTION), 3.0)
            self.db.set_reply_state(user_id, time.time() + new_r, True)

    def set_task(self, user_id: int, task: asyncio.Task, reply_at: float):
        self._tasks[user_id] = task
        self.db.set_reply_state(user_id, reply_at, True)


# ─────────────────────────────────────────────────────────────────────────────
# MOOD DECAY
# ─────────────────────────────────────────────────────────────────────────────

async def mood_decay_loop(db: DB):
    while True:
        await asyncio.sleep(3600)
        try:
            for uid in db.all_user_ids():
                last = db.get_last_seen(uid)
                if last and (time.time() - last) > 3600:
                    db.set_mood_score(uid, db.get_mood_score(uid) - MOOD_IDLE_DECAY)
        except Exception as e:
            log.error(f"Mood decay error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# PROACTIVE SCHEDULER
# ─────────────────────────────────────────────────────────────────────────────

class ProactiveScheduler:
    def __init__(self, bot: Bot, db: DB, brain: AnyaBrain, ve: VoiceEngine):
        self.bot   = bot
        self.db    = db
        self.brain = brain
        self.ve    = ve

    def _next_ts(self) -> float:
        return time.time() + random.uniform(PROACTIVE_MIN_H, PROACTIVE_MAX_H) * 3600

    async def run(self):
        log.info("Проактивный планировщик запущен")
        while True:
            try:
                await self._tick()
            except Exception as e:
                log.error(f"Proactive scheduler error: {e}")
            await asyncio.sleep(60)

    async def _tick(self):
        now  = time.time()
        hour = msk_hour()

        for uid in self.db.all_user_ids():
            if not is_sleeping() and self.db.sleep_has_queue(uid):
                missed = self.db.sleep_pop(uid)
                text   = await self.brain.morning_wakeup(uid, missed)
                await self._send(uid, text)
                self.db.set_next_proactive(uid, self._next_ts())
                continue

            if is_sleeping() or hour < 9 or hour >= 22:
                continue

            nxt = self.db.get_next_proactive(uid)
            if nxt is None:
                self.db.set_next_proactive(uid, self._next_ts())
            elif now >= nxt:
                text = await self.brain.proactive_msg(uid)
                await self._send(uid, text)
                self.db.set_next_proactive(uid, self._next_ts())

    async def _send(self, user_id: int, text: str):
        try:
            sentences = split_sentences(text)
            for s in sentences:
                await self.bot.send_chat_action(user_id, ChatAction.TYPING)
                await typing_delay(s)
                await self.bot.send_message(user_id, s)
            self.db.add_msg(user_id, "assistant", text)
            log.info(f"Proactive → {user_id}: {text[:50]}")
        except Exception as e:
            log.error(f"Proactive send error {user_id}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# BOT INIT
# ─────────────────────────────────────────────────────────────────────────────

bot_obj = Bot(token=TELEGRAM_TOKEN)
dp      = Dispatcher()
db      = DB(DB_PATH)
brain   = AnyaBrain(db)
ve      = VoiceEngine(bot_obj)
engine  = ReplyEngine(db)
buf     = MessageBuffer()


# ─────────────────────────────────────────────────────────────────────────────
# SEND
# ─────────────────────────────────────────────────────────────────────────────

async def send(message: Message, text: str, user_id: int, save: bool = True):
    if not text or not text.strip():
        log.warning(f"send() получил пустой текст для {user_id}, пропускаю")
        return

    if save:
        db.add_msg(user_id, "assistant", text)

    sentences = [s for s in split_sentences(text) if s.strip()]
    if not sentences:
        log.warning(f"split_sentences вернул пустой список для {user_id}")
        return

    for i, sentence in enumerate(sentences):
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        await typing_delay(sentence)

        # Опечатка
        if random.random() < TYPO_CHANCE:
            typo = add_typo(sentence)
            if typo and typo != sentence:
                await message.answer(typo)
                await asyncio.sleep(random.uniform(0.8, 2.0))
                orig_words = sentence.split()
                typo_words = typo.split()
                fixed = None
                for o, t in zip(orig_words, typo_words):
                    if o != t:
                        fixed = o + "*"
                        break
                if fixed:
                    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
                    await asyncio.sleep(0.5)
                    await message.answer(fixed)
                continue

        # Голос на последнем предложении
        if i == len(sentences) - 1 and random.random() < VOICE_CHANCE:
            audio = await ve.synthesize(sentence)
            if audio:
                try:
                    await message.answer_voice(BufferedInputFile(audio, filename="anya.mp3"))
                    continue
                except Exception as e:
                    log.error(f"Voice send error: {e}")

        await message.answer(sentence)


async def maybe_react(message: Message, text: str) -> bool:
    reaction = await brain.should_react_only(text)
    if not reaction:
        return False
    try:
        from aiogram.types import ReactionTypeEmoji
        await bot_obj.set_message_reaction(
            message.chat.id, message.message_id,
            [ReactionTypeEmoji(emoji=reaction)]
        )
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CORE HANDLER
# ─────────────────────────────────────────────────────────────────────────────

async def process_messages(message: Message, texts: list[str], uid: int, name: str):
    if random.random() < READ_DELAY_CHANCE:
        delay = random.randint(READ_DELAY_MIN, READ_DELAY_MAX)
        log.info(f"Задержка прочтения для {uid}: {delay}с")
        await asyncio.sleep(delay)

    if is_sleeping() and SLEEP_CHANCE > 0 and random.random() < SLEEP_CHANCE:
        for t in texts:
            db.sleep_enqueue(uid, t)
        log.info(f"Режим сна: {len(texts)} сообщ. от {uid} в очереди")
        return

    if engine.is_pending(uid):
        for t in texts:
            db.sleep_enqueue(uid, t)
        engine.spam_reduce(uid)
        return

    if len(texts) == 1 and await maybe_react(message, texts[0]):
        db.add_msg(uid, "user", texts[0])
        db.set_last_seen(uid, time.time())
        return

    combined = " ".join(texts)
    extra = f"Пользователь написал несколько сообщений подряд: {' / '.join(texts)}" if len(texts) > 1 else ""

    delay = engine.calc_delay(uid)
    db.set_last_seen(uid, time.time())

    for t in texts:
        db.add_msg(uid, "user", t)

    if delay <= 0:
        reply = await brain.chat(uid, combined, extra=extra)
        await send(message, reply, uid)
    else:
        for t in texts:
            db.sleep_enqueue(uid, t)

        async def delayed_task():
            reply_at = time.time() + delay
            engine.set_task(uid, asyncio.current_task(), reply_at)
            while True:
                current_ra, _ = db.get_reply_state(uid)
                remaining = (current_ra or reply_at) - time.time()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(1.0, remaining))
            queued = db.sleep_pop(uid)
            if not queued:
                db.clear_reply_state(uid)
                return
            combined_q = " ".join(queued)
            extra_q = (f"Пока не отвечала, пришло несколько сообщений: {' / '.join(queued)}"
                       if len(queued) > 1 else "")
            reply = await brain.chat(uid, combined_q, extra=extra_q)
            db.clear_reply_state(uid)
            await send(message, reply, uid)

        task = asyncio.create_task(delayed_task())
        engine.set_task(uid, task, time.time() + delay)


async def handle_incoming(message: Message, text: str, uid: int, name: str):
    db.ensure_user(uid, name)
    db.set_last_seen(uid, time.time())

    if is_hurry_msg(text) and (engine.is_pending(uid) or buf.is_waiting(uid)):
        reply = random.choice(HURRY_REPLIES)
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        await asyncio.sleep(random.uniform(0.5, 1.5))
        await message.answer(reply)
        if engine.is_pending(uid):
            engine.spam_reduce(uid)
        return

    async def on_buffer_ready(msg: Message, msgs: list[str]):
        await process_messages(msg, msgs, uid, name)

    buf.push(uid, text, message, on_buffer_ready)


# ─────────────────────────────────────────────────────────────────────────────
# HANDLERS
# ─────────────────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(msg: Message):
    uid  = msg.from_user.id
    name = msg.from_user.first_name or "ты"
    db.ensure_user(uid, name)
    db.set_last_seen(uid, time.time())
    reply = await brain.chat(
        uid, f"Привет, меня зовут {name}",
        extra=f"Первое сообщение от {name}. Скажи привет по-своему, не банально."
    )
    await send(msg, reply, uid)


@dp.message(Command("forget"))
async def cmd_forget(msg: Message):
    db.clear(msg.from_user.id)
    await msg.answer("окей, всё удалила... но тебя всё равно помню")


@dp.message(Command("city"))
async def cmd_city(msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer("напиши: /city Москва")
        return
    city = parts[1].strip()
    db.set_city(msg.from_user.id, city)
    weather = await get_weather(city)
    await msg.answer(f"запомнила: {city}" + (f". Сейчас там: {weather}" if weather else ""))


@dp.message(Command("mood"))
async def cmd_mood(msg: Message):
    uid   = msg.from_user.id
    score = db.get_mood_score(uid)
    level = mood_level(score)
    labels = {"great":"отличное","good":"хорошее","neutral":"нормальное","bad":"плохое","sad":"грустное"}
    await msg.answer(f"моё настроение: {labels[level]} ({score}/100)")


@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "просто пиши мне\n\n"
        "голосовые — расшифрую\n"
        "фото — оценю\n"
        "иногда отвечу голосом или поставлю реакцию\n"
        "настроение меняется\n\n"
        "/city Москва — твой город (для погоды)\n"
        "/mood — моё настроение\n"
        "/forget — стереть историю"
    )


@dp.message(F.voice)
async def handle_voice(msg: Message):
    uid  = msg.from_user.id
    name = msg.from_user.first_name or "ты"
    await msg.answer("секунду, слушаю...")
    transcript = await ve.transcribe(msg.voice)
    if not transcript:
        await msg.answer("не расслышала, напиши текстом")
        return
    await handle_incoming(msg, f"[ГС]: {transcript}", uid, name)


@dp.message(F.photo)
async def handle_photo(msg: Message):
    uid     = msg.from_user.id
    name    = msg.from_user.first_name or "ты"
    caption = msg.caption or ""
    db.ensure_user(uid, name)
    db.set_last_seen(uid, time.time())
    reply = await brain.analyze_photo(uid, caption)
    db.add_msg(uid, "user",      f"[фото]{': ' + caption if caption else ''}")
    db.add_msg(uid, "assistant", reply)
    await send(msg, reply, uid, save=False)


@dp.message(F.text)
async def handle_text(msg: Message):
    await handle_incoming(msg, msg.text, msg.from_user.id, msg.from_user.first_name or "ты")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    scheduler = ProactiveScheduler(bot_obj, db, brain, ve)
    asyncio.create_task(scheduler.run())
    asyncio.create_task(mood_decay_loop(db))
    log.info(f"Саша v5.4 (GPTunnel) запущена — модель: {MAIN_MODEL}")
    await dp.start_polling(bot_obj, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())