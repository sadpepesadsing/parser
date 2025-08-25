import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from config import API_TOKEN
from database.db import init_db, add_user_channel, add_monitor_channel, get_user_channels

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ===== КЛАВИАТУРА =====
builder = InlineKeyboardBuilder()
builder.add(InlineKeyboardButton(text="📌 Мои каналы", callback_data='my_channels'))
builder.add(InlineKeyboardButton(text="➕ Добавить канал", callback_data='add_channel'))
builder.add(InlineKeyboardButton(text="ℹ️ Справка", callback_data='info'))
builder.adjust(2)
main_menu = builder.as_markup()

async def make_channels_buttons(channels: tuple):
    builder = InlineKeyboardBuilder()
    for channel in channels:
        builder.add(InlineKeyboardButton(text=channel, callback_data=channel))
    builder.adjust(2)
    channels_btns = builder.as_markup()
    return channels_btns

# ===== ХЭНДЛЕРЫ =====
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer("Привет! 👋 Я бот для мониторинга каналов.\nВыбери действие:", reply_markup=main_menu)

@dp.callback_query(lambda c: c.data == "info")
async def cmd_help(callback: types.CallbackQuery):
    await callback.message.answer("❓ Справка:\n\n"
                         "📌 'Мой канал' — укажи свой канал.\n"
                         "➕ 'Добавить канал для мониторинга' — добавь каналы, за которыми следить.\n"
                         "Можно добавлять несколько!")

# ===== МОЙ КАНАЛ =====
@dp.callback_query(lambda c: c.data == "my_channels")
async def ask_user_channel(callback: types.CallbackQuery):
    await callback.message.answer("...")
    user_id = callback.from_user.id
    channels = await get_user_channels(user_id)
    btns = await make_channels_buttons(channels)
    await callback.message.answer("Выбери канал", reply_markup=btns)
    #дальше не ебу че делать тут типа кнопочки с каналами
    #короче я спать хочу хз разберешься или нет что тут к чему
    #завтра постараюсь что-нибудь незначительное пописать
    #если приеду завтра и не усну, а каскад будет почти готов, попробую ебануть штуку с мониторингом каналов
    #он просто у меня уже получался в одном лишь файле мейн, но я не ебу как это должно работать в полноценном сервисе,
    #а так как у меня гпт сдох, ждем завтрашнего дня


# ===== ДОБАВИТЬ КАНАЛ ДЛЯ МОНИТОРИНГА =====
@dp.callback_query(lambda c: c.data == "add_channel")
async def ask_monitor_channel(callback: types.CallbackQuery):
    await callback.message.answer("Отправь ссылку на свой канал")
    dp.message.register(save_user_channel, lambda m: m.from_user.id == callback.from_user.id)

async def save_user_channel(message: types.Message):
    user_id = message.from_user.id
    user_channel = message.text.strip()
    await add_user_channel(user_id, user_channel)
    await message.answer(f"✅ Твой канал сохранён: {user_channel}", reply_markup=main_menu)

async def save_monitor_channel(message: types.Message):
    user_id = message.from_user.id
    monitor_channel = message.text.strip()
    await add_monitor_channel(user_id, monitor_channel)
    await message.answer(f"✅ Канал {monitor_channel} добавлен для мониторинга!", reply_markup=main_menu)

# ===== ЗАПУСК =====
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
