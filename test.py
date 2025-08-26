from telethon import TelegramClient, events

api_id = 1234567  # реальное число с my.telegram.org
api_hash = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"  # строка 32 символа
phone = "+16318956428"  # номер телефона в международном формате

client = TelegramClient("my_session", api_id, api_hash)

@client.on(events.NewMessage(chats=["@pqpqpqllllll"]))
async def handler(event):
    print(f"Новый пост: {event.message.text}")

client.start()
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