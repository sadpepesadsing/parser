import aiosqlite
from typing import List, Tuple, Optional
from config import DB_NAME

# Нормализация
def normalize_channel_link(link: str) -> str:
    link = link.strip()
    if link.startswith("https://t.me/"):
        username_part = link.replace("https://t.me/", "")
        return f"@{username_part}" if not username_part.startswith('+') else link
    elif link.startswith("t.me/"):
        username_part = link.replace("t.me/", "")
        return f"@{username_part}" if not username_part.startswith('+') else f"https://{link}"
    elif link.startswith("@"):
        return link
    else:
        return link

class Database:
    """Класс для работы с базой данных"""
    def __init__(self, db_name: str = DB_NAME):
        self.db_name = db_name

    async def _execute(self, query: str, params: tuple = ()) -> None:
        async with aiosqlite.connect(self.db_name) as db:
            try:
                await db.execute(query, params)
                await db.commit()
            except aiosqlite.Error as e:
                raise ValueError(f"Database error: {e}")

    async def _fetchall(self, query: str, params: tuple = ()) -> List[tuple]:
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute(query, params) as cursor:
                return await cursor.fetchall()

    async def _fetchone(self, query: str, params: tuple = ()) -> Optional[tuple]:
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute(query, params) as cursor:
                return await cursor.fetchone()

# Глобальный экземпляр
db = Database()

async def init_db():
    """Инициализирует базу данных"""
    queries = [
        # Таблица пользователей с составным PRIMARY KEY
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER,
            user_channel TEXT,
            PRIMARY KEY (user_id, user_channel)
        )
        """,
        # Таблица каналов для мониторинга с UNIQUE
        """
        CREATE TABLE IF NOT EXISTS monitor_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_channel TEXT,
            monitor_channel TEXT,
            is_subscribed INTEGER DEFAULT 0,
            UNIQUE (user_channel, monitor_channel),
            FOREIGN KEY(user_channel) REFERENCES users(user_channel) ON DELETE CASCADE
        )
        """,
        # Таблица последних постов
        """
        CREATE TABLE IF NOT EXISTS last_posts (
            monitor_channel TEXT PRIMARY KEY,
            last_post_id INTEGER DEFAULT 0
        )
        """,
        # Индексы для производительности
        "CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_monitor_user_channel ON monitor_channels(user_channel)",
        "CREATE INDEX IF NOT EXISTS idx_monitor_monitor_channel ON monitor_channels(monitor_channel)"
    ]
    for query in queries:
        await db._execute(query)

async def add_user_channel(user_id: int, user_channel: str) -> None:
    """Добавляет пользовательский канал"""
    user_channel = normalize_channel_link(user_channel)
    if not user_channel:
        raise ValueError("Invalid channel link")
    query = "INSERT OR IGNORE INTO users (user_id, user_channel) VALUES (?, ?)"
    await db._execute(query, (user_id, user_channel))

async def add_monitor_channel(user_channel: str, monitor_channel: str) -> None:
    """Добавляет канал для мониторинга"""
    monitor_channel = normalize_channel_link(monitor_channel)
    if not monitor_channel:
        raise ValueError("Invalid monitor channel link")
    query = "INSERT INTO monitor_channels (user_channel, monitor_channel) VALUES (?, ?)"
    await db._execute(query, (user_channel, monitor_channel))

async def remove_monitor_channel(user_channel: str, monitor_channel: str) -> None:
    """Удаляет канал из мониторинга"""
    query = "DELETE FROM monitor_channels WHERE user_channel = ? AND monitor_channel = ?"
    await db._execute(query, (user_channel, monitor_channel))
    # Также удаляем last_post если больше нет ссылок (optional)
    if not await get_monitor_channels(monitor_channel):  # Если нет user_channels для этого monitor
        await db._execute("DELETE FROM last_posts WHERE monitor_channel = ?", (monitor_channel,))

# Остальные функции без изменений
async def set_channel_subscribed(monitor_channel: str, subscribed: bool = True) -> None:
    query = "UPDATE monitor_channels SET is_subscribed = ? WHERE monitor_channel = ?"
    await db._execute(query, (1 if subscribed else 0, monitor_channel))

async def is_channel_subscribed(monitor_channel: str) -> bool:
    query = "SELECT is_subscribed FROM monitor_channels WHERE monitor_channel = ? LIMIT 1"
    result = await db._fetchone(query, (monitor_channel,))
    return bool(result and result[0]) if result else False

async def get_channels_to_subscribe() -> Tuple[str]:
    query = "SELECT DISTINCT monitor_channel FROM monitor_channels WHERE is_subscribed = 0"
    rows = await db._fetchall(query)
    return tuple(row[0] for row in rows)

async def get_user_channels(user_id: int) -> Tuple[str]:
    query = "SELECT user_channel FROM users WHERE user_id = ?"
    rows = await db._fetchall(query, (user_id,))
    return tuple(row[0] for row in rows)

async def get_monitor_channels(user_channel: str) -> Tuple[str]:
    query = "SELECT monitor_channel FROM monitor_channels WHERE user_channel = ?"
    rows = await db._fetchall(query, (user_channel,))
    return tuple(row[0] for row in rows)

async def user_channel_exists(user_id: int, user_channel: str) -> bool:
    """Проверяет существование пользовательского канала для конкретного пользователя"""
    query = "SELECT 1 FROM users WHERE user_id = ? AND user_channel = ?"
    result = await db._fetchone(query, (user_id, user_channel))
    return result is not None

async def get_last_post_id(monitor_channel: str) -> int:
    query = "SELECT last_post_id FROM last_posts WHERE monitor_channel = ?"
    result = await db._fetchone(query, (monitor_channel,))
    return result[0] if result else 0

async def update_last_post_id(monitor_channel: str, post_id: int) -> None:
    query = "INSERT OR REPLACE INTO last_posts (monitor_channel, last_post_id) VALUES (?, ?)"
    await db._execute(query, (monitor_channel, post_id))

async def get_target_channels(monitor_channel: str) -> Tuple[str]:
    query = """
        SELECT DISTINCT u.user_channel
        FROM users u
        JOIN monitor_channels mc ON u.user_channel = mc.user_channel
        WHERE mc.monitor_channel = ?
    """
    rows = await db._fetchall(query, (monitor_channel,))
    return tuple(row[0] for row in rows)

async def get_all_monitor_channels() -> Tuple[str]:
    query = "SELECT DISTINCT monitor_channel FROM monitor_channels"
    rows = await db._fetchall(query)
    return tuple(row[0] for row in rows)