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
            user_id INTEGER,
            channel TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
        """)

        #хочу сделать таблицу (канал, айди), чтобы боту легко было понять, кому отправить пост
        await db.execute("""
        CREATE TABLE IF NOT EXISTS channels_users (
            channel TEXT,
            user_id INTEGER,
            PRIMARY KEY (channel, user_id)
        )
        """)
        await db.commit()

async def add_user_channel(user_id: int, user_channel: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        INSERT OR IGNORE INTO users (user_id, user_channel) VALUES (?, ?)
        """, (user_id, user_channel))
        await db.commit()

async def add_monitor_channel(user_id: int, channel: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        INSERT INTO monitor_channels (user_id, channel) VALUES (?, ?)
        """, (user_id, channel))
        await db.commit()

#добавленные каналы у пользователя
async def get_user_channels(user_id: int) -> tuple[str, ...]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
                "SELECT user_channel FROM users WHERE user_id = ?",
                (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return tuple(row[0] for row in rows)