"""VK Music Bridge: save VK music links in a private Telegram chat.

This version stores links only and searches the user's own saved links.
It does not download or redistribute audio.
"""
import asyncio
import logging
from html import escape
from contextlib import contextmanager
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

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
    # Additive schema only: existing saved_links rows and IDs are never rewritten.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS favorites (
            telegram_user_id INTEGER NOT NULL,
            link_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (telegram_user_id, link_id),
            FOREIGN KEY (link_id) REFERENCES saved_links(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (telegram_user_id, name)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS playlist_links (
            playlist_id INTEGER NOT NULL,
            link_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (playlist_id, link_id),
            FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
            FOREIGN KEY (link_id) REFERENCES saved_links(id) ON DELETE CASCADE
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
    escaped = normalized.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    with database() as connection:
        return connection.execute(
            """
            SELECT id, url, created_at FROM saved_links
            WHERE telegram_user_id = ? AND url LIKE ? ESCAPE '!'
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



def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Поиск по библиотеке", callback_data="menu:search"),
         InlineKeyboardButton(text="📚 Библиотека", callback_data="menu:library")],
        [InlineKeyboardButton(text="⭐ Избранное", callback_data="menu:favorites"),
         InlineKeyboardButton(text="🎼 Плейлисты", callback_data="menu:playlists")],
        [InlineKeyboardButton(text="❔ Помощь", callback_data="menu:help")],
    ])


def link_actions_keyboard(user_id: int, link_id: int) -> InlineKeyboardMarkup:
    with database() as connection:
        row = connection.execute(
            "SELECT 1 FROM favorites WHERE telegram_user_id = ? AND link_id = ?",
            (user_id, link_id),
        ).fetchone()
        link = connection.execute(
            "SELECT url FROM saved_links WHERE telegram_user_id = ? AND id = ?",
            (user_id, link_id),
        ).fetchone()
    fav_label = "💔 Убрать из избранного" if row else "⭐ В избранное"
    buttons = [
        [InlineKeyboardButton(text=fav_label, callback_data=f"fav:{link_id}")],
        [InlineKeyboardButton(text="➕ В плейлист", callback_data=f"playlist:add:{link_id}")],
    ]
    if link:
        buttons.append([InlineKeyboardButton(text="↗️ Открыть ссылку", url=link["url"])])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def show_library(message: Message, user_id: int) -> None:
    rows = get_links(user_id)
    if not rows:
        await message.answer(
            "Библиотека пока пуста. Пришли ссылку VK, чтобы сохранить её.",
            reply_markup=main_menu_keyboard(),
        )
        return
    await message.answer("<b>Твоя библиотека</b> · последние 10 ссылок")
    for row in rows:
        safe_url = (row["url"].replace("&", "&amp;")
                    .replace("<", "&lt;").replace(">", "&gt;"))
        await message.answer(
            f"<b>ID {row['id']}</b>\n{safe_url}\n\n"
            "Можно добавить запись в избранное или плейлист.",
            reply_markup=link_actions_keyboard(user_id, int(row["id"])),
            disable_web_page_preview=True,
        )
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard())


def get_favorites(user_id: int) -> list[sqlite3.Row]:
    with database() as connection:
        return connection.execute(
            """
            SELECT s.id, s.url, s.created_at
            FROM saved_links s JOIN favorites f ON f.link_id = s.id
            WHERE f.telegram_user_id = ? AND s.telegram_user_id = ?
            ORDER BY f.created_at DESC LIMIT 20
            """, (user_id, user_id)
        ).fetchall()


def get_playlists(user_id: int) -> list[sqlite3.Row]:
    with database() as connection:
        return connection.execute(
            "SELECT id, name FROM playlists WHERE telegram_user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()


def playlist_keyboard(playlists: list[sqlite3.Row], link_id: int | None = None) -> InlineKeyboardMarkup:
    rows = []
    for playlist in playlists:
        if link_id is None:
            rows.append([InlineKeyboardButton(
                text=f"🎼 {playlist['name']}",
                callback_data=f"playlist:view:{playlist['id']}",
            )])
        else:
            rows.append([InlineKeyboardButton(
                text=f"➕ {playlist['name']}",
                callback_data=f"playlist:put:{playlist['id']}:{link_id}",
            )])
    rows.append([InlineKeyboardButton(text="📚 В меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data.startswith("menu:"))
async def menu_callback(callback) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    if callback.message.chat.type != "private":
        await callback.answer("Открой меню в личном чате.", show_alert=True)
        return
    action = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    await callback.answer()
    if action == "home":
        await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    elif action == "library":
        await show_library(callback.message, user_id)
    elif action == "favorites":
        rows = get_favorites(user_id)
        if not rows:
            await callback.message.answer("Избранное пока пусто.", reply_markup=main_menu_keyboard())
            return
        for row in rows:
            safe_url = (row["url"].replace("&", "&amp;")
                        .replace("<", "&lt;").replace(">", "&gt;"))
            await callback.message.answer(
                f"<b>ID {row['id']}</b>\n{safe_url}",
                reply_markup=link_actions_keyboard(user_id, int(row["id"])),
                disable_web_page_preview=True,
            )
    elif action == "playlists":
        playlists = get_playlists(user_id)
        await callback.message.answer(
            "🎼 <b>Твои плейлисты</b>\n"
            "Создать новый: <code>/newplaylist Название</code>",
            reply_markup=playlist_keyboard(playlists),
        )
    elif action == "search":
        await callback.message.answer(
            "Пришли команду <code>/search часть-ссылки</code>. "
            "Поиск по названию и исполнителю подключим после появления разрешённого API.",
            reply_markup=main_menu_keyboard(),
        )
    elif action == "help":
        await callback.message.answer(
            "Пришли ссылку VK — она сохранится в библиотеке.\n"
            "/newplaylist Название — создать плейлист.\n"
            "/search текст — найти сохранённую ссылку.\n"
            "/delete ID — удалить ссылку.",
            reply_markup=main_menu_keyboard(),
        )


@dp.callback_query(F.data.startswith("fav:"))
async def favorite_callback(callback) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    if callback.message.chat.type != "private":
        await callback.answer("Доступно только в личном чате.", show_alert=True)
        return
    try:
        link_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректная запись.", show_alert=True)
        return
    user_id = callback.from_user.id
    with database() as connection:
        owned = connection.execute(
            "SELECT 1 FROM saved_links WHERE id = ? AND telegram_user_id = ?",
            (link_id, user_id),
        ).fetchone()
        if not owned:
            await callback.answer("Запись не найдена в твоей библиотеке.", show_alert=True)
            return
        exists = connection.execute(
            "SELECT 1 FROM favorites WHERE telegram_user_id = ? AND link_id = ?",
            (user_id, link_id),
        ).fetchone()
        if exists:
            connection.execute(
                "DELETE FROM favorites WHERE telegram_user_id = ? AND link_id = ?",
                (user_id, link_id),
            )
            text = "Удалено из избранного."
        else:
            connection.execute(
                "INSERT OR IGNORE INTO favorites (telegram_user_id, link_id) VALUES (?, ?)",
                (user_id, link_id),
            )
            text = "Добавлено в избранное ⭐"
    await callback.answer(text)
    await callback.message.edit_reply_markup(
        reply_markup=link_actions_keyboard(user_id, link_id)
    )


@dp.message(Command("newplaylist"))
async def new_playlist_handler(message: Message) -> None:
    if message.chat.type != "private":
        await message.answer("Создавать плейлисты можно только в личном чате.")
        return
    if message.from_user is None:
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Укажи название: <code>/newplaylist Ночной вайб</code>")
        return
    name = parts[1].strip()
    if not name or len(name) > 40 or any(ord(ch) < 32 for ch in name):
        await message.answer("Название должно содержать от 1 до 40 обычных символов.")
        return
    try:
        with database() as connection:
            connection.execute(
                "INSERT INTO playlists (telegram_user_id, name) VALUES (?, ?)",
                (message.from_user.id, name),
            )
    except sqlite3.IntegrityError:
        await message.answer("Плейлист с таким названием уже существует.")
        return
    await message.answer(f"Плейлист «{escape(name)}» создан! 🎼", reply_markup=main_menu_keyboard())


@dp.callback_query(F.data.startswith("playlist:add:"))
async def playlist_add_callback(callback) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    if callback.message.chat.type != "private":
        await callback.answer("Доступно только в личном чате.", show_alert=True)
        return
    try:
        link_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректная запись.", show_alert=True)
        return
    with database() as connection:
        owned = connection.execute(
            "SELECT 1 FROM saved_links WHERE id = ? AND telegram_user_id = ?",
            (link_id, callback.from_user.id),
        ).fetchone()
    if not owned:
        await callback.answer("Эта ссылка не принадлежит твоей библиотеке.", show_alert=True)
        return
    playlists = get_playlists(callback.from_user.id)
    await callback.answer()
    if not playlists:
        await callback.message.answer(
            "Сначала создай плейлист командой <code>/newplaylist Название</code>."
        )
        return
    await callback.message.answer("Выбери плейлист:", reply_markup=playlist_keyboard(playlists, link_id))


@dp.callback_query(F.data.startswith("playlist:put:"))
async def playlist_put_callback(callback) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    if callback.message.chat.type != "private":
        await callback.answer("Доступно только в личном чате.", show_alert=True)
        return
    try:
        _, _, playlist_id, link_id = callback.data.split(":")
        playlist_id, link_id = int(playlist_id), int(link_id)
    except (ValueError, AttributeError):
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    user_id = callback.from_user.id
    with database() as connection:
        owned_playlist = connection.execute(
            "SELECT 1 FROM playlists WHERE id = ? AND telegram_user_id = ?",
            (playlist_id, user_id),
        ).fetchone()
        owned_link = connection.execute(
            "SELECT 1 FROM saved_links WHERE id = ? AND telegram_user_id = ?",
            (link_id, user_id),
        ).fetchone()
        if not owned_playlist or not owned_link:
            await callback.answer("Плейлист или ссылка не найдены.", show_alert=True)
            return
        connection.execute(
            "INSERT OR IGNORE INTO playlist_links (playlist_id, link_id) VALUES (?, ?)",
            (playlist_id, link_id),
        )
    await callback.answer("Добавлено в плейлист 🎼")


@dp.callback_query(F.data.startswith("playlist:view:"))
async def playlist_view_callback(callback) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    if callback.message.chat.type != "private":
        await callback.answer("Доступно только в личном чате.", show_alert=True)
        return
    try:
        playlist_id = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await callback.answer("Некорректный плейлист.", show_alert=True)
        return
    with database() as connection:
        playlist = connection.execute(
            "SELECT name FROM playlists WHERE id = ? AND telegram_user_id = ?",
            (playlist_id, callback.from_user.id),
        ).fetchone()
        rows = connection.execute(
            """
            SELECT s.id, s.url FROM saved_links s
            JOIN playlist_links p ON p.link_id = s.id
            JOIN playlists pl ON pl.id = p.playlist_id
            WHERE pl.id = ? AND pl.telegram_user_id = ? AND s.telegram_user_id = ?
            ORDER BY p.created_at DESC LIMIT 30
            """, (playlist_id, callback.from_user.id, callback.from_user.id)
        ).fetchall() if playlist else []
    await callback.answer()
    if not playlist:
        await callback.message.answer("Плейлист не найден.")
        return
    lines = [f"<b>🎼 {escape(playlist['name'])}</b>"]
    for row in rows:
        safe_url = (row["url"].replace("&", "&amp;")
                    .replace("<", "&lt;").replace(">", "&gt;"))
        lines.append(f"\n<b>ID {row['id']}</b> · {safe_url}")
    if not rows:
        lines.append("\nПока пусто — добавь ссылки через библиотеку.")
    await callback.message.answer("\n".join(lines), disable_web_page_preview=True,
                                  reply_markup=main_menu_keyboard())

@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    if message.chat.type != "private":
        await message.answer("Открой меня в личном чате, чтобы сохранять свои ссылки.")
        return
    await message.answer(
        "Привет! Я <b>VK Music Bridge 2.0</b> 🎵\n\n"
        "Отправь ссылку VK, чтобы сохранить её. Используй меню для библиотеки, избранного и плейлистов.\n\n"
        "<i>Пока я сохраняю ссылки и не скачиваю аудио.</i>",
        reply_markup=main_menu_keyboard(),
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
        "Поиск пока работает только по URL в твоей библиотеке, а не по каталогу аудио VK.\n\n"
        "/newplaylist Название — создать плейлист."
    , reply_markup=main_menu_keyboard())


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
    await show_library(message, message.from_user.id)


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
