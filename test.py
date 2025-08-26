from telethon import TelegramClient, events

api_id = 24296340
api_hash = "27f2c8f4ea5a997a0314ac812ed04317"
phone = "+16318956428"  # номер телефона в международном формате

client = TelegramClient("user_session", api_id, api_hash)

@client.on(events.NewMessage(chats=["@pqpqpqllllll"]))
async def handler(event):
    print(f"Новый пост: {event.message.text}")

client.start(phone)
client.run_until_disconnected()


# import sqlite3
#
# # Подключаемся (если файла нет — создастся)
# conn = sqlite3.connect("bot.db")
# cur = conn.cursor()
#
# # Создаём таблицу (один раз)
# cur.execute("""
# CREATE TABLE IF NOT EXISTS messages (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     user_id INTEGER,
#     text TEXT
# )
# """)
