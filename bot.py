"""VK Music Bridge: save VK music links in a private Telegram chat.

This version stores links only and searches the user's own saved links.
It does not download or redistribute audio.
"""
import asyncio
import logging
from contextlib import contextmanager
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from config import BOT_TOKEN, DATABASE_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

dp = Dispatcher()

URL_PATTERN = re.compile(r"https?://[^\s<>]+|(?:www\.)?(?:music\.)?(?:m\.)?(?:vk\.com|vk\.ru)/[^\s<>]+", re.IGNORECASE)
ALLOWED_HOSTS = {"vk.com", "www.vk.com", "m.vk.com", "music.vk.com", "vk.ru", "www.vk.ru"}
MAX_SEARCH_LENGTH = 80
MAX_SEARCH_RESULTS = 10


def get_connection() -> sqlite3.Connection:
    """Open a SQLite connection and ensure the schema exists."""
    path = Path(DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_user_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(telegram_user_id, url)
        )
        """
    )
    connection.commit()
    return connection


@contextmanager
def database():
    """Commit successful operations and always close the SQLite connection."""
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def normalize_vk_url(raw_url: str) -> str | None:
    """Accept only VK domains and reject URLs with misleading hostnames."""
    candidate = raw_url.strip().rstrip(".,!?;:)]}")
    if not candidate.lower().startswith(("http://", "https://")):
        candidate = "https://" + candidate
    try:
        parsed = urlparse(candidate)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return None

    if parsed.scheme not in {"http", "https"} or host not in ALLOWED_HOSTS:
        return None
    if parsed.username or parsed.password:
        return None
    return parsed.geturl()


def extract_vk_links(text: str) -> list[str]:
    found: list[str] = []
    for match in URL_PATTERN.findall(text):
        url = normalize_vk_url(match)
        if url and url not in found:
            found.append(url)
    return found


def save_link(user_id: int, url: str) -> tuple[bool, int]:
    with database() as connection:
        cursor = connection.execute(
            "INSERT OR IGNORE INTO saved_links (telegram_user_id, url) VALUES (?, ?)",
            (user_id, url),
        )
        row = connection.execute(
            "SELECT id FROM saved_links WHERE telegram_user_id = ? AND url = ?",
            (user_id, url),
        ).fetchone()
        return cursor.rowcount == 1, int(row["id"])


def get_links(user_id: int, limit: int = 10) -> list[sqlite3.Row]:
    with database() as connection:
        return connection.execute(
            """
            SELECT id, url, created_at FROM saved_links
            WHERE telegram_user_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()


def search_links(user_id: int, query: str, limit: int = MAX_SEARCH_RESULTS) -> list[sqlite3.Row]:
    """Search only the requesting user's saved URLs; query is always parameterized."""
    normalized = query.strip()
    if not normalized or len(normalized) > MAX_SEARCH_LENGTH:
        return []
    # Escape SQL LIKE metacharacters so user input is treated literally.
    escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    with database() as connection:
        return connection.execute(
            """
            SELECT id, url, created_at FROM saved_links
            WHERE telegram_user_id = ? AND url LIKE ? ESCAPE '\\'
            ORDER BY id DESC LIMIT ?
            """,
            (user_id, f"%{escaped}%", min(max(int(limit), 1), MAX_SEARCH_RESULTS)),
        ).fetchall()


def delete_link(user_id: int, link_id: int) -> bool:
    with database() as connection:
        cursor = connection.execute(
            "DELETE FROM saved_links WHERE telegram_user_id = ? AND id = ?",
            (user_id, link_id),
        )
        return cursor.rowcount > 0


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    if message.chat.type != "private":
        await message.answer("Открой меня в личном чате, чтобы сохранять свои ссылки.")
        return
    await message.answer(
        "Привет! Я <b>VK Music Bridge</b> 🎵\n\n"
        "Отправь ссылку VK — я сохраню её в твою личную библиотеку.\n\n"
        "Команды:\n"
        "/library — последние сохранённые ссылки\n"
        "/search текст — поиск по твоим сохранённым ссылкам\n"
        "/delete ID — удалить ссылку по её номеру\n"
        "/help — помощь\n\n"
        "<i>Я сохраняю ссылки, а не скачиваю аудиофайлы.</i>"
    )


@dp.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "<b>Как пользоваться</b>\n"
        "1. Пришли ссылку с домена vk.com или vk.ru.\n"
        "2. Я сохраню её в твоей библиотеке.\n"
        "3. /library — посмотреть последние записи.\n"
        "4. /search текст — найти ссылку по части адреса.\n"
        "5. /delete ID — удалить запись.\n\n"
        "Поиск пока работает только по URL в твоей библиотеке, а не по каталогу аудио VK."
    )


@dp.message(Command("search"))
async def search_handler(message: Message) -> None:
    if message.chat.type != "private":
        await message.answer("Поиск личной библиотеки доступен только в личном чате.")
        return
    if message.from_user is None:
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip():
        await message.answer(
            "Напиши часть ссылки для поиска.\nПример: <code>/search vk.com</code>\n"
            "Сейчас поиск работает по адресам в твоей библиотеке."
        )
        return
    query = parts[1].strip()
    if len(query) > MAX_SEARCH_LENGTH:
        await message.answer(f"Запрос слишком длинный. Максимум — {MAX_SEARCH_LENGTH} символов.")
        return
    rows = search_links(message.from_user.id, query)
    if not rows:
        await message.answer("Ничего не найдено в твоей библиотеке. Попробуй другую часть ссылки.")
        return
    lines = [f"<b>Результаты поиска:</b> {len(rows)}"]
    for row in rows:
        safe_url = (row["url"].replace("&", "&amp;")
                    .replace("<", "&lt;").replace(">", "&gt;"))
        lines.append(f"\n<b>ID {row['id']}</b> · {safe_url}")
    lines.append("\n\nУдалить запись: <code>/delete ID</code>")
    await message.answer("\n".join(lines), disable_web_page_preview=True)


@dp.message(Command("library"))
async def library_handler(message: Message) -> None:
    if message.chat.type != "private":
        await message.answer("Открой меня в личном чате, чтобы посмотреть свою библиотеку.")
        return
    if message.from_user is None:
        return
    rows = get_links(message.from_user.id)
    if not rows:
        await message.answer("Библиотека пока пуста. Пришли ссылку VK, чтобы сохранить её.")
        return

    lines = ["<b>Твоя библиотека</b> (последние 10 ссылок):"]
    for row in rows:
        safe_url = (row["url"].replace("&", "&amp;")
                    .replace("<", "&lt;").replace(">", "&gt;"))
        lines.append(f"\n<b>ID {row['id']}</b> · {safe_url}")
    lines.append("\n\nУдалить запись: <code>/delete ID</code>")
    await message.answer("\n".join(lines), disable_web_page_preview=True)


@dp.message(Command("delete"))
async def delete_handler(message: Message) -> None:
    if message.chat.type != "private":
        await message.answer("Удалять ссылки можно только в личном чате со мной.")
        return
    if message.from_user is None:
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Укажи номер записи: <code>/delete 12</code>")
        return
    link_id = int(parts[1])
    if delete_link(message.from_user.id, link_id):
        await message.answer(f"Ссылка с ID {link_id} удалена.")
    else:
        await message.answer("Не нашёл такую запись в твоей библиотеке.")


@dp.message(F.text)
async def text_handler(message: Message) -> None:
    if message.chat.type != "private":
        return
    if message.from_user is None or message.text is None:
        return

    links = extract_vk_links(message.text)
    if not links:
        await message.answer(
            "Я пока умею сохранять ссылки VK. Пришли ссылку вида "
            "<code>https://vk.com/...</code>."
        )
        return

    saved_count = 0
    duplicate_count = 0
    for url in links:
        was_saved, _ = save_link(message.from_user.id, url)
        if was_saved:
            saved_count += 1
        else:
            duplicate_count += 1

    response = []
    if saved_count:
        response.append(f"Сохранено ссылок: <b>{saved_count}</b> 🎵")
    if duplicate_count:
        response.append(f"Уже были в библиотеке: <b>{duplicate_count}</b>.")
    response.append("Посмотреть библиотеку: /library")
    response.append("Поиск по сохранённым ссылкам: <code>/search часть-ссылки</code>")
    await message.answer("\n".join(response), disable_web_page_preview=True)


async def main() -> None:
    with database():
        pass

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        logger.info("Starting VK Music Bridge bot")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
