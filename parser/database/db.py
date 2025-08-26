import aiosqlite
from config import DB_NAME

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Таблица пользователей (user_id, личный канал)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER,
            user_channel TEXT PRIMARY KEY
        )
        """)

        # Таблица каналов для мониторинга
        await db.execute("""
        CREATE TABLE IF NOT EXISTS monitor_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_channel TEXT,
            monitor_channel TEXT,
            is_subscribed INTEGER DEFAULT 0,
            FOREIGN KEY(user_channel) REFERENCES users(user_channel)
        )
        """)

        # Таблица для хранения последних проверенных постов
        await db.execute("""
        CREATE TABLE IF NOT EXISTS last_posts (
            monitor_channel TEXT PRIMARY KEY,
            last_post_id INTEGER DEFAULT 0
        )
        """)
        await db.commit()

# Функции для работы с подписками
async def set_channel_subscribed(monitor_channel: str, subscribed: bool = True):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        UPDATE monitor_channels SET is_subscribed = ? WHERE monitor_channel = ?
        """, (1 if subscribed else 0, monitor_channel))
        await db.commit()

async def is_channel_subscribed(monitor_channel: str) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
                "SELECT is_subscribed FROM monitor_channels WHERE monitor_channel = ? LIMIT 1",
                (monitor_channel,)
        ) as cursor:
            result = await cursor.fetchone()
            return bool(result[0]) if result else False

async def get_channels_to_subscribe() -> tuple[str]:
    """Получить каналы, на которые нужно подписаться"""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("""
            SELECT DISTINCT monitor_channel 
            FROM monitor_channels 
            WHERE is_subscribed = 0
        """) as cursor:
            rows = await cursor.fetchall()
            return tuple(row[0] for row in rows)

async def add_user_channel(user_id: int, user_channel: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        INSERT OR IGNORE INTO users (user_id, user_channel) VALUES (?, ?)
        """, (user_id, user_channel))
        await db.commit()

async def add_monitor_channel(user_channel: str, monitor_channel: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        INSERT INTO monitor_channels (user_channel, monitor_channel) VALUES (?, ?)
        """, (user_channel, monitor_channel))
        await db.commit()

# Получить все каналы пользователя
async def get_user_channels(user_id: int) -> tuple[str, ...]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
                "SELECT user_channel FROM users WHERE user_id = ?",
                (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return tuple(row[0] for row in rows)

# Получить все мониторинговые каналы для пользовательского канала
async def get_monitor_channels(user_channel: str) -> tuple[str, ...]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
                "SELECT monitor_channel FROM monitor_channels WHERE user_channel = ?",
                (user_channel,)
        ) as cursor:
            rows = await cursor.fetchall()
            return tuple(row[0] for row in rows)

# Проверить существует ли пользовательский канал
async def user_channel_exists(user_channel: str) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
                "SELECT 1 FROM users WHERE user_channel = ?",
                (user_channel,)
        ) as cursor:
            return await cursor.fetchone() is not None

# Удалить мониторинговый канал
async def remove_monitor_channel(user_channel: str, monitor_channel: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
                "DELETE FROM monitor_channels WHERE user_channel = ? AND monitor_channel = ?",
                (user_channel, monitor_channel)
        )
        await db.commit()

async def get_last_post_id(monitor_channel: str) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
                "SELECT last_post_id FROM last_posts WHERE monitor_channel = ?",
                (monitor_channel,)
        ) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

async def update_last_post_id(monitor_channel: str, post_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        INSERT OR REPLACE INTO last_posts (monitor_channel, last_post_id) VALUES (?, ?)
        """, (monitor_channel, post_id))
        await db.commit()

# Получить всех пользователей, которые мониторят канал
async def get_users_monitoring_channel(monitor_channel: str) -> tuple[int]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("""
            SELECT DISTINCT u.user_id 
            FROM users u 
            JOIN monitor_channels mc ON u.user_channel = mc.user_channel 
            WHERE mc.monitor_channel = ?
        """, (monitor_channel,)) as cursor:
            rows = await cursor.fetchall()
            return tuple(row[0] for row in rows)

# Получить все уникальные каналы для мониторинга
async def get_all_monitor_channels() -> tuple[str]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT DISTINCT monitor_channel FROM monitor_channels") as cursor:
            rows = await cursor.fetchall()
            return tuple(row[0] for row in rows)
