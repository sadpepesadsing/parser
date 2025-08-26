import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from config import API_TOKEN
from database.db import init_db, add_user_channel, add_monitor_channel, get_user_channels, get_monitor_channels, user_channel_exists, remove_monitor_channel

# Инициализация с MemoryStorage
storage = MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=storage)

# Состояния для FSM
class Form(StatesGroup):
    waiting_for_user_channel = State()
    waiting_for_monitor_channel = State()

# Словарь для хранения ID последних сообщений
user_last_messages = {}

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
async def delete_previous_messages(user_id: int):
    """Удаляет предыдущие сообщения пользователя"""
    if user_id in user_last_messages:
        for msg_id in user_last_messages[user_id]:
            try:
                await bot.delete_message(user_id, msg_id)
            except:
                pass
        user_last_messages[user_id] = []

async def send_message_with_cleanup(user_id: int, text: str, reply_markup=None):
    """Отправляет сообщение с очисткой предыдущих"""
    await delete_previous_messages(user_id)
    message = await bot.send_message(user_id, text, reply_markup=reply_markup)
    if user_id not in user_last_messages:
        user_last_messages[user_id] = []
    user_last_messages[user_id].append(message.message_id)
    return message

# ===== КЛАВИАТУРЫ =====
def get_main_menu():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📌 Мои каналы", callback_data='my_channels'))
    builder.add(InlineKeyboardButton(text="➕ Добавить канал", callback_data='add_channel'))
    builder.add(InlineKeyboardButton(text="ℹ️ Справка", callback_data='info'))
    builder.adjust(2)
    return builder.as_markup()

def get_back_home_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="◀️ Назад", callback_data='back'))
    builder.add(InlineKeyboardButton(text="🏠 Домой", callback_data='home'))
    return builder.as_markup()

def get_channel_management_keyboard(user_channel: str):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="👀 Показать мониторинг", callback_data=f'show_monitor:{user_channel}'))
    builder.add(InlineKeyboardButton(text="➕ Добавить мониторинг", callback_data=f'add_monitor:{user_channel}'))
    builder.add(InlineKeyboardButton(text="◀️ Назад", callback_data='back_to_channels'))
    builder.add(InlineKeyboardButton(text="🏠 Домой", callback_data='home'))
    builder.adjust(2)
    return builder.as_markup()

def get_monitor_channels_keyboard(monitor_channels: tuple, user_channel: str):
    builder = InlineKeyboardBuilder()
    for channel in monitor_channels:
        builder.add(InlineKeyboardButton(text=f"❌ {channel}", callback_data=f'remove_monitor:{user_channel}:{channel}'))
    builder.add(InlineKeyboardButton(text="➕ Добавить ещё", callback_data=f'add_monitor:{user_channel}'))
    builder.add(InlineKeyboardButton(text="◀️ Назад", callback_data=f'back_to_channel:{user_channel}'))
    builder.add(InlineKeyboardButton(text="🏠 Домой", callback_data='home'))
    builder.adjust(1)
    return builder.as_markup()

async def make_channels_buttons(channels: tuple):
    builder = InlineKeyboardBuilder()
    for channel in channels:
        builder.add(InlineKeyboardButton(text=channel, callback_data=f'select_channel:{channel}'))
    builder.add(InlineKeyboardButton(text="➕ Добавить свой канал", callback_data='add_user_channel_btn'))
    builder.add(InlineKeyboardButton(text="◀️ Назад", callback_data='back'))
    builder.add(InlineKeyboardButton(text="🏠 Домой", callback_data='home'))
    builder.adjust(1)
    return builder.as_markup()

# ===== ХЭНДЛЕРЫ =====
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await send_message_with_cleanup(message.from_user.id, 
                                  "Привет! 👋 Я бот для мониторинга каналов.\nВыбери действие:", 
                                  reply_markup=get_main_menu())

@dp.callback_query(lambda c: c.data == "info")
async def cmd_help(callback: types.CallbackQuery):
    await send_message_with_cleanup(callback.from_user.id,
                                  "❓ Справка:\n\n"
                                  "📌 'Мой канал' — укажи свой канал.\n"
                                  "➕ 'Добавить канал для мониторинга' — добавь каналы, за которыми следить.\n"
                                  "Можно добавлять несколько!", 
                                  reply_markup=get_back_home_keyboard())
    await callback.answer()

# ===== МОЙ КАНАЛ =====
@dp.callback_query(lambda c: c.data == "my_channels")
async def user_channels(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    channels = await get_user_channels(user_id)
    
    if not channels:
        await send_message_with_cleanup(user_id, 
                                      "У тебя пока нет добавленных каналов. Хочешь добавить?", 
                                      reply_markup=get_back_home_keyboard())
    else:
        btns = await make_channels_buttons(channels)
        await send_message_with_cleanup(user_id, 
                                      "📋 Твои каналы:\n\nВыбери канал для управления:", 
                                      reply_markup=btns)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('select_channel:'))
async def select_user_channel(callback: types.CallbackQuery):
    user_channel = callback.data.split(':')[1]
    keyboard = get_channel_management_keyboard(user_channel)
    await send_message_with_cleanup(callback.from_user.id, 
                                  f"📊 Управление каналом: {user_channel}\n\nЧто хочешь сделать?", 
                                  reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('show_monitor:'))
async def show_monitor_channels(callback: types.CallbackQuery):
    user_channel = callback.data.split(':')[1]
    monitor_channels = await get_monitor_channels(user_channel)
    
    if not monitor_channels:
        await send_message_with_cleanup(callback.from_user.id, 
                                      f"📭 Для канала {user_channel} нет добавленных каналов для мониторинга.", 
                                      reply_markup=get_channel_management_keyboard(user_channel))
    else:
        channels_list = "\n".join([f"• {channel}" for channel in monitor_channels])
        keyboard = get_monitor_channels_keyboard(monitor_channels, user_channel)
        await send_message_with_cleanup(callback.from_user.id, 
                                      f"📋 Каналы для мониторинга ({user_channel}):\n\n{channels_list}", 
                                      reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('add_monitor:'))
async def add_monitor_channel_handler(callback: types.CallbackQuery, state: FSMContext):
    user_channel = callback.data.split(':')[1]
    await state.update_data(user_channel=user_channel)
    await state.set_state(Form.waiting_for_monitor_channel)
    await send_message_with_cleanup(callback.from_user.id, 
                                  f"📩 Отправь ссылку на канал для мониторинга (для {user_channel}):", 
                                  reply_markup=get_back_home_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('remove_monitor:'))
async def remove_monitor_channel_handler(callback: types.CallbackQuery):
    data = callback.data.split(':')
    user_channel = data[1]
    monitor_channel = data[2]
    
    await remove_monitor_channel(user_channel, monitor_channel)
    await send_message_with_cleanup(callback.from_user.id, 
                                  f"✅ Канал {monitor_channel} удалён из мониторинга!", 
                                  reply_markup=get_back_home_keyboard())
    
    # Обновляем список мониторинговых каналов
    monitor_channels = await get_monitor_channels(user_channel)
    if monitor_channels:
        channels_list = "\n".join([f"• {channel}" for channel in monitor_channels])
        keyboard = get_monitor_channels_keyboard(monitor_channels, user_channel)
        await send_message_with_cleanup(callback.from_user.id, 
                                      f"📋 Обновлённый список каналов для мониторинга:\n\n{channels_list}", 
                                      reply_markup=keyboard)
    else:
        await send_message_with_cleanup(callback.from_user.id, 
                                      "📭 Больше нет каналов для мониторинга.", 
                                      reply_markup=get_channel_management_keyboard(user_channel))
    await callback.answer()

# ===== ДОБАВЛЕНИЕ КАНАЛОВ =====
@dp.callback_query(lambda c: c.data == "add_channel")
async def add_user_channel_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_user_channel)
    await send_message_with_cleanup(callback.from_user.id, 
                                  "📩 Отправь ссылку на свой канал:", 
                                  reply_markup=get_back_home_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "add_user_channel_btn")
async def add_user_channel_btn(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_user_channel)
    await send_message_with_cleanup(callback.from_user.id, 
                                  "📩 Отправь ссылку на свой канал:", 
                                  reply_markup=get_back_home_keyboard())
    await callback.answer()

# Обработка ввода пользовательского канала
@dp.message(Form.waiting_for_user_channel)
async def save_user_channel(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_channel = message.text.strip()
    
    await add_user_channel(user_id, user_channel)
    await state.clear()
    await send_message_with_cleanup(user_id, 
                                  f"✅ Твой канал сохранён: {user_channel}", 
                                  reply_markup=get_main_menu())

# Обработка ввода мониторингового канала
@dp.message(Form.waiting_for_monitor_channel)
async def save_monitor_channel(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    monitor_channel = message.text.strip()
    
    # Получаем user_channel из состояния
    data = await state.get_data()
    user_channel = data.get("user_channel")
    
    if user_channel and await user_channel_exists(user_channel):
        await add_monitor_channel(user_channel, monitor_channel)
        await state.clear()
        
        # Просто добавляем в базу, подписка произойдет при следующей проверке
        await send_message_with_cleanup(user_id, 
                                  f"✅ Канал {monitor_channel} добавлен для мониторинга!\n"
                                  f"Бот попытается подписаться на него в течение 5 минут.", 
                                  reply_markup=get_main_menu())
    else:
        await send_message_with_cleanup(user_id, 
                                  "❌ Ошибка: твой канал не найден. Добавь его сначала.", 
                                  reply_markup=get_main_menu())
        await state.clear()

# ===== НАВИГАЦИЯ =====
@dp.callback_query(lambda c: c.data == "home")
async def go_home(callback: types.CallbackQuery):
    await send_message_with_cleanup(callback.from_user.id, 
                                  "🏠 Главное меню:", 
                                  reply_markup=get_main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back")
async def go_back(callback: types.CallbackQuery):
    await send_message_with_cleanup(callback.from_user.id, 
                                  "◀️ Возврат:", 
                                  reply_markup=get_main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_channels")
async def back_to_channels(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    channels = await get_user_channels(user_id)
    if channels:
        btns = await make_channels_buttons(channels)
        await send_message_with_cleanup(user_id, 
                                      "📋 Твои каналы:\n\nВыбери канал для управления:", 
                                      reply_markup=btns)
    else:
        await send_message_with_cleanup(user_id, 
                                      "У тебя пока нет добавленных каналов. Хочешь добавить?", 
                                      reply_markup=get_back_home_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('back_to_channel:'))
async def back_to_channel(callback: types.CallbackQuery):
    user_channel = callback.data.split(':')[1]
    keyboard = get_channel_management_keyboard(user_channel)
    await send_message_with_cleanup(callback.from_user.id, 
                                  f"📊 Управление каналом: {user_channel}\n\nЧто хочешь сделать?", 
                                  reply_markup=keyboard)
    await callback.answer()

# ===== ЗАПУСК =====
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
