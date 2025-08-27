import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import API_TOKEN
from database.db import (
    init_db, add_user_channel, add_monitor_channel,
    get_user_channels, get_monitor_channels,
    user_channel_exists, remove_monitor_channel
)

# Импортируем монитор
from monitor import run_monitor

# Инициализация бота
storage = MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=storage)

# Состояния FSM
class Form(StatesGroup):
    waiting_for_user_channel = State()
    waiting_for_monitor_channel = State()

# Словарь для хранения ID последних сообщений
user_last_messages = {}

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
def normalize_channel_link(link: str) -> str:
    """Нормализует ссылку на канал к единому формату"""
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

async def delete_previous_messages(user_id: int):
    """Удаляет предыдущие сообщения пользователя"""
    if user_id in user_last_messages:
        for msg_id in user_last_messages[user_id]:
            try:
                await bot.delete_message(user_id, msg_id)
            except Exception:
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
def create_main_menu() -> InlineKeyboardMarkup:
    """Создает главное меню"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📌 Мои каналы", callback_data='my_channels'),
        InlineKeyboardButton(text="➕ Добавить канал", callback_data='add_channel')
    )
    builder.row(InlineKeyboardButton(text="ℹ️ Справка", callback_data='info'))
    return builder.as_markup()

def create_back_home_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопками Назад и Домой"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data='back'),
        InlineKeyboardButton(text="🏠 Домой", callback_data='home')
    )
    return builder.as_markup()

def create_channel_management_keyboard(user_channel: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру управления каналом"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👀 Показать мониторинг", callback_data=f'show_monitor:{user_channel}'),
        InlineKeyboardButton(text="➕ Добавить мониторинг", callback_data=f'add_monitor:{user_channel}')
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data='back_to_channels'),
        InlineKeyboardButton(text="🏠 Домой", callback_data='home')
    )
    return builder.as_markup()

def create_monitor_channels_keyboard(monitor_channels: tuple, user_channel: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру каналов мониторинга"""
    builder = InlineKeyboardBuilder()

    for channel in monitor_channels:
        builder.row(InlineKeyboardButton(
            text=f"❌ {channel}",
            callback_data=f'remove_monitor:{user_channel}:{channel}'
        ))

    builder.row(InlineKeyboardButton(
        text="➕ Добавить ещё",
        callback_data=f'add_monitor:{user_channel}'
    ))
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data=f'back_to_channel:{user_channel}'),
        InlineKeyboardButton(text="🏠 Домой", callback_data='home')
    )

    return builder.as_markup()

async def create_channels_list_keyboard(channels: tuple) -> InlineKeyboardMarkup:
    """Создает клавиатуру со списком каналов"""
    builder = InlineKeyboardBuilder()

    for channel in channels:
        builder.row(InlineKeyboardButton(
            text=channel,
            callback_data=f'select_channel:{channel}'
        ))

    builder.row(InlineKeyboardButton(
        text="➕ Добавить свой канал",
        callback_data='add_user_channel_btn'
    ))
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data='back'),
        InlineKeyboardButton(text="🏠 Домой", callback_data='home')
    )

    return builder.as_markup()

# ===== ОБРАБОТЧИКИ КОМАНД =====
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    await send_message_with_cleanup(
        message.from_user.id,
        "Привет! 👋 Я бот для мониторинга каналов.\nВыбери действие:",
        reply_markup=create_main_menu()
    )

@dp.callback_query(F.data == "info")
async def show_info(callback: types.CallbackQuery):
    """Показывает справку"""
    help_text = (
        "❓ Справка:\n\n"
        "📌 'Мой канал' — укажи свой канал.\n"
        "➕ 'Добавить канал для мониторинга' — добавь каналы, за которыми следить.\n"
        "Можно добавлять несколько!"
    )

    await send_message_with_cleanup(
        callback.from_user.id,
        help_text,
        reply_markup=create_back_home_keyboard()
    )
    await callback.answer()

# ===== ОБРАБОТЧИКИ МОИХ КАНАЛОВ =====
@dp.callback_query(F.data == "my_channels")
async def show_user_channels(callback: types.CallbackQuery):
    """Показывает каналы пользователя"""
    user_id = callback.from_user.id
    channels = await get_user_channels(user_id)
    keyboard = await create_channels_list_keyboard(channels)

    if not channels:
        message_text = "У тебя пока нет добавленных каналов. Хочешь добавить?"
        await send_message_with_cleanup(user_id, message_text, create_back_home_keyboard())
    else:
        keyboard = await create_channels_list_keyboard(channels)
        await send_message_with_cleanup(user_id, "📋 Твои каналы:\n\nВыбери канал для управления:", keyboard)

    await callback.answer()

@dp.callback_query(F.data.startswith('select_channel:'))
async def handle_channel_selection(callback: types.CallbackQuery):
    """Обрабатывает выбор канала"""
    user_channel = callback.data.split(':')[1]
    keyboard = create_channel_management_keyboard(user_channel)

    await send_message_with_cleanup(
        callback.from_user.id,
        f"📊 Управление каналом: {user_channel}\n\nЧто хочешь сделать?",
        keyboard
    )
    await callback.answer()

# ===== ОБРАБОТЧИКИ МОНИТОРИНГА =====
@dp.callback_query(F.data.startswith('show_monitor:'))
async def show_monitor_channels(callback: types.CallbackQuery):
    """Показывает каналы для мониторинга"""
    user_channel = callback.data.split(':')[1]
    monitor_channels = await get_monitor_channels(user_channel)

    if not monitor_channels:
        message_text = f"📭 Для канала {user_channel} нет добавленных каналов для мониторинга."
        await send_message_with_cleanup(callback.from_user.id, message_text,
                                        create_channel_management_keyboard(user_channel))
    else:
        channels_list = "\n".join([f"• {channel}" for channel in monitor_channels])
        keyboard = create_monitor_channels_keyboard(monitor_channels, user_channel)

        await send_message_with_cleanup(
            callback.from_user.id,
            f"📋 Каналы для мониторинга ({user_channel}):\n\n{channels_list}",
            keyboard
        )

    await callback.answer()

@dp.callback_query(F.data.startswith('add_monitor:'))
async def start_add_monitor_channel(callback: types.CallbackQuery, state: FSMContext):
    """Начинает процесс добавления канала мониторинга"""
    user_channel = callback.data.split(':')[1]
    await state.update_data(user_channel=user_channel)
    await state.set_state(Form.waiting_for_monitor_channel)

    await send_message_with_cleanup(
        callback.from_user.id,
        f"📩 Отправь ссылку на канал для мониторинга (для {user_channel}):",
        create_back_home_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith('remove_monitor:'))
async def handle_remove_monitor(callback: types.CallbackQuery):
    """Удаляет канал из мониторинга"""
    data = callback.data.split(':')
    user_channel, monitor_channel = data[1], data[2]

    await remove_monitor_channel(user_channel, monitor_channel)
    await send_message_with_cleanup(
        callback.from_user.id,
        f"✅ Канал {monitor_channel} удалён из мониторинга!",
        create_back_home_keyboard()
    )

    # Обновляем список
    monitor_channels = await get_monitor_channels(user_channel)
    if monitor_channels:
        channels_list = "\n".join([f"• {channel}" for channel in monitor_channels])
        keyboard = create_monitor_channels_keyboard(monitor_channels, user_channel)
        await send_message_with_cleanup(
            callback.from_user.id,
            f"📋 Обновлённый список каналов для мониторинга:\n\n{channels_list}",
            keyboard
        )
    else:
        await send_message_with_cleanup(
            callback.from_user.id,
            "📭 Больше нет каналов для мониторинга.",
            create_channel_management_keyboard(user_channel)
        )

    await callback.answer()

# ===== ОБРАБОТЧИКИ ДОБАВЛЕНИЯ КАНАЛОВ =====
@dp.callback_query(F.data == "add_channel")
@dp.callback_query(F.data == "add_user_channel_btn")
async def start_add_user_channel(callback: types.CallbackQuery, state: FSMContext):
    """Начинает процесс добавления пользовательского канала"""
    await state.set_state(Form.waiting_for_user_channel)
    await send_message_with_cleanup(
        callback.from_user.id,
        "📩 Отправь ссылку на свой канал:",
        create_back_home_keyboard()
    )
    await callback.answer()

@dp.message(Form.waiting_for_user_channel)
async def save_user_channel(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_channel = normalize_channel_link(message.text.strip())
    try:
        await add_user_channel(user_id, user_channel)
        await state.clear()
        await send_message_with_cleanup(
            user_id,
            f"✅ Твой канал сохранён: {user_channel}",
            create_main_menu()
        )
    except Exception as e:
        await state.clear()
        await send_message_with_cleanup(
            user_id,
            f"❌ Ошибка: {str(e)}. Попробуй другую ссылку.",
            create_main_menu()
        )

@dp.message(Form.waiting_for_monitor_channel)
async def save_monitor_channel(message: types.Message, state: FSMContext):
    """Сохраняет канал для мониторинга"""
    user_id = message.from_user.id
    monitor_channel = normalize_channel_link(message.text.strip())
    data = await state.get_data()
    user_channel = data.get("user_channel")

    if not user_channel or not await user_channel_exists(user_id, user_channel):
        await state.clear()
        await send_message_with_cleanup(
            user_id,
            "❌ Ошибка: ваш канал не найден. Добавьте его сначала через 'Мои каналы'.",
            create_main_menu()
        )
        return

    try:
        await add_monitor_channel(user_channel, monitor_channel)
        await state.clear()
        await send_message_with_cleanup(
            user_id,
            f"✅ Канал {monitor_channel} добавлен для мониторинга!\n"
            f"Бот попытается подписаться на него в ближайшее время.\n"
            f"Для приватных каналов可能需要 подтверждение администратора.",
            create_main_menu()
        )
    except Exception as e:
        await state.clear()
        await send_message_with_cleanup(
            user_id,
            f"❌ Ошибка: {str(e)}. Возможно, канал уже добавлен или неверная ссылка.",
            create_main_menu()
        )

# ===== ОБРАБОТЧИКИ НАВИГАЦИИ =====
@dp.callback_query(F.data == "home")
async def go_to_home(callback: types.CallbackQuery):
    """Переходит на главную"""
    await send_message_with_cleanup(
        callback.from_user.id,
        "🏠 Главное меню:",
        create_main_menu()
    )
    await callback.answer()

@dp.callback_query(F.data == "back")
async def go_back(callback: types.CallbackQuery):
    """Возвращает назад"""
    await send_message_with_cleanup(
        callback.from_user.id,
        "◀️ Возврат:",
        create_main_menu()
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_channels")
async def back_to_channels_list(callback: types.CallbackQuery):
    """Возвращает к списку каналов"""
    user_id = callback.from_user.id
    channels = await get_user_channels(user_id)

    if channels:
        keyboard = await create_channels_list_keyboard(channels)
        await send_message_with_cleanup(user_id, "📋 Твои каналы:\n\nВыбери канал для управления:", keyboard)
    else:
        await send_message_with_cleanup(
            user_id,
            "У тебя пока нет добавленных каналов. Хочешь добавить?",
            create_back_home_keyboard()
        )

    await callback.answer()

@dp.callback_query(F.data.startswith('back_to_channel:'))
async def back_to_channel_management(callback: types.CallbackQuery):
    """Возвращает к управлению каналом"""
    user_channel = callback.data.split(':')[1]
    keyboard = create_channel_management_keyboard(user_channel)

    await send_message_with_cleanup(
        callback.from_user.id,
        f"📊 Управление каналом: {user_channel}\n\nЧто хочешь сделать?",
        keyboard
    )
    await callback.answer()

# ===== ЗАПУСК =====
async def main():
    """Основная функция запуска"""
    await init_db()

    # Запускаем бота и монитор параллельно
    bot_task = asyncio.create_task(dp.start_polling(bot))
    monitor_task = asyncio.create_task(run_monitor())

    # Ожидаем завершения обеих задач
    await asyncio.gather(bot_task, monitor_task)

if __name__ == "__main__":
    asyncio.run(main())
