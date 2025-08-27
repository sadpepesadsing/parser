# monitor.py
import asyncio
import logging
from typing import List, Optional
import io
import sys

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import BufferedInputFile, InlineKeyboardButton
from telethon import TelegramClient, errors
from telethon.tl.types import Message, Channel
from telethon.tl.functions.channels import JoinChannelRequest

from config import API_ID, API_HASH, CHECK_INTERVAL, PHONE_NUMBER, API_TOKEN
from database.db import (
    get_all_monitor_channels, get_last_post_id, update_last_post_id,
    set_channel_subscribed, is_channel_subscribed, get_channels_to_subscribe,
    get_target_channels, normalize_channel_link, get_user_id_by_channel
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Глобальный словарь для pending постов
pending_posts = {}

class ChannelMonitor:
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.is_running = False
        self.is_connected = False
        self.bot = Bot(token=API_TOKEN)

    async def input_code_callback(self):
        """Функция для ввода кода подтверждения из консоли"""
        print("На ваш телефон отправлен код подтверждения. Введите его:")
        code = input("Код: ").strip()
        return code

    async def ensure_connection(self) -> bool:
        if self.is_connected and self.client and self.client.is_connected():
            return True
        try:
            if self.client:
                await self.client.disconnect()

            # Создаем клиент с обработчиками для ввода кода и пароля
            self.client = TelegramClient(
                'user_session',
                API_ID,
                API_HASH
            )

            # Запускаем клиент с обработкой кода подтверждения
            await self.client.start(
                phone=PHONE_NUMBER,
                code_callback=self.input_code_callback,
                password=self.input_password_callback
            )

            self.is_connected = True
            logger.info("Соединение с Telegram установлено")
            return True

        except errors.FloodWaitError as e:
            logger.warning(f"Flood wait: sleeping {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
            return await self.ensure_connection()
        except errors.SessionPasswordNeededError:
            logger.warning("Требуется двухфакторная аутентификация")
            # Пароль будет запрошен через callback
            return await self.ensure_connection()
        except Exception as e:
            logger.error(f"Ошибка подключения: {e}")
            self.is_connected = False
            return False

    async def start(self):
        self.is_running = True
        logger.info("Монитор каналов запущен")
        if await self.ensure_connection():
            await self.subscribe_to_channels()
        asyncio.create_task(self.periodic_check())

    async def stop(self):
        self.is_running = False
        if self.client and self.client.is_connected():
            await self.client.disconnect()
        self.is_connected = False
        await self.bot.session.close()
        logger.info("Монитор каналов остановлен")

    async def subscribe_to_channels(self):
        try:
            if not await self.ensure_connection():
                logger.error("Не удалось установить соединение для подписки")
                return
            channels_to_subscribe = await get_channels_to_subscribe()
            logger.info(f"Найдено {len(channels_to_subscribe)} каналов для подписки")
            for channel_username in channels_to_subscribe:
                try:
                    success = await self.subscribe_to_channel(channel_username)
                    if success:
                        await set_channel_subscribed(channel_username, True)
                        logger.info(f"Успешно подписались на {channel_username}")
                    else:
                        logger.warning(f"Не удалось подписаться на {channel_username}")
                    await asyncio.sleep(5)
                except errors.FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logger.error(f"Ошибка подписки на {channel_username}: {e}")
        except Exception as e:
            logger.error(f"Ошибка в subscribe_to_channels: {e}")

    async def subscribe_to_channel(self, channel_username: str) -> bool:
        try:
            if not await self.ensure_connection():
                logger.error("Нет соединения для подписки")
                return False

            # Нормализуем канал
            normalized_channel = normalize_channel_link(channel_username)
            if normalized_channel.startswith('@'):
                channel_username = normalized_channel[1:]
            else:
                channel_username = normalized_channel

            logger.info(f"Попытка подписки на канал: {channel_username}")

            # Пробуем получить entity канала
            try:
                entity = await self.client.get_entity(channel_username)
            except ValueError:
                # Если не получается найти по username, пробуем как invite link
                try:
                    entity = await self.client.get_entity(normalized_channel)
                except Exception as e:
                    logger.error(f"Не удалось найти канал {channel_username}: {e}")
                    return False

            # Подписываемся на канал
            result = await self.client(JoinChannelRequest(entity))
            logger.info(f"Результат подписки на {channel_username}: {result}")

            await asyncio.sleep(2)
            return True

        except errors.ChannelInvalidError:
            logger.error(f"Неверный канал: {channel_username}")
            return False
        except errors.ChannelPrivateError:
            logger.error(f"Канал приватный: {channel_username}")
            return False
        except errors.InviteRequestSentError:
            logger.warning(f"Запрос на вступление отправлен для {channel_username}")
            return True
        except errors.UserAlreadyParticipantError:
            logger.info(f"Уже подписан на {channel_username}")
            return True
        except errors.FloodWaitError as e:
            logger.warning(f"Flood wait: sleeping {e.seconds} seconds для {channel_username}")
            await asyncio.sleep(e.seconds)
            return await self.subscribe_to_channel(channel_username)
        except Exception as e:
            logger.error(f"Ошибка подписки на {channel_username}: {e}")
            return False

    async def get_channel_entity(self, channel_username: str):
        try:
            if not await self.ensure_connection():
                return None

            # Нормализуем канал
            normalized_channel = normalize_channel_link(channel_username)
            if normalized_channel.startswith('@'):
                channel_username = normalized_channel[1:]
            else:
                channel_username = normalized_channel

            entity = await self.client.get_entity(channel_username)
            return entity
        except Exception as e:
            logger.error(f"Ошибка получения канала {channel_username}: {e}")
            return None

    async def get_new_posts(self, channel_username: str) -> List[Message]:
        try:
            if not await self.ensure_connection():
                return []

            # Проверяем, подписан ли уже на канал
            if not await is_channel_subscribed(channel_username):
                logger.info(f"Пытаемся подписаться на {channel_username}")
                success = await self.subscribe_to_channel(channel_username)
                if success:
                    await set_channel_subscribed(channel_username, True)
                    logger.info(f"Успешно подписались на {channel_username} и обновили статус в БД")
                else:
                    logger.warning(f"Не удалось подписаться на {channel_username}")
                    return []

            entity = await self.get_channel_entity(channel_username)
            if not entity:
                logger.warning(f"Не удалось получить entity для канала {channel_username}")
                return []

            last_post_id = await get_last_post_id(channel_username)
            messages = []

            # Получаем сообщения, начиная с последнего известного ID
            async for message in self.client.iter_messages(entity, min_id=last_post_id, limit=5):
                if message.id > last_post_id and (message.message or message.media):
                    messages.append(message)

            if messages:
                # Сортируем сообщения по ID в порядке возрастания
                messages.sort(key=lambda m: m.id)
                latest_id = messages[-1].id
                await update_last_post_id(channel_username, latest_id)
                logger.info(f"Найдено {len(messages)} новых постов в {channel_username}")

            return messages

        except errors.FloodWaitError as e:
            logger.warning(f"Flood wait: sleeping {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
            return await self.get_new_posts(channel_username)
        except Exception as e:
            logger.error(f"Ошибка получения постов из {channel_username}: {e}")
            return []

    async def process_message(self, message: Message, monitor_channel: str):
        global pending_posts
        try:
            target_channels = await get_target_channels(monitor_channel)
            if not target_channels:
                return

            media_data = None
            media_type = None
            if message.media:
                media_data = await message.download_media(bytes)
                if media_data:
                    if hasattr(message.media, 'photo'):
                        media_type = 'photo'
                    else:
                        media_type = 'document'
                else:
                    logger.warning(f"Не удалось скачать медиа для поста {message.id} из {monitor_channel}")

            post_key = f"{monitor_channel}:{message.id}"
            pending_posts[post_key] = {
                'text': message.message or '',
                'media_data': media_data,
                'media_type': media_type,
                'pending_targets': set(target_channels)
            }

            text_preview = f"Новый пост из {monitor_channel}\n\n{message.message or '[Медиа без текста]'}"

            for target_channel in target_channels:
                user_id = await get_user_id_by_channel(target_channel)
                if user_id:
                    builder = InlineKeyboardBuilder()
                    builder.row(
                        InlineKeyboardButton(text="Опубликовать", callback_data=f'publish:{post_key}:{target_channel}'),
                        InlineKeyboardButton(text="Отклонить", callback_data=f'reject:{post_key}:{target_channel}')
                    )
                    keyboard = builder.as_markup()

                    try:
                        if media_data:
                            if media_type == 'photo':
                                await self.bot.send_photo(
                                    chat_id=user_id,
                                    photo=BufferedInputFile(media_data, filename="photo.jpg"),
                                    caption=text_preview,
                                    reply_markup=keyboard
                                )
                            else:
                                await self.bot.send_document(
                                    chat_id=user_id,
                                    document=BufferedInputFile(media_data, filename="media"),
                                    caption=text_preview,
                                    reply_markup=keyboard
                                )
                        else:
                            await self.bot.send_message(
                                chat_id=user_id,
                                text=text_preview,
                                reply_markup=keyboard
                            )
                        logger.info(f"✅ Preview отправлен пользователю {user_id} для {target_channel}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка отправки preview пользователю {user_id}: {e}")
                else:
                    logger.warning(f"Не найден user_id для {target_channel}")

        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")

    async def check_channels(self):
        try:
            if not await self.ensure_connection():
                logger.warning("Пропускаем проверку - нет соединения")
                return

            monitor_channels = await get_all_monitor_channels()
            logger.info(f"Проверяем {len(monitor_channels)} каналов")

            for channel in monitor_channels:
                try:
                    new_posts = await self.get_new_posts(channel)
                    for post in new_posts:
                        await self.process_message(post, channel)
                        await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Ошибка проверки канала {channel}: {e}")

        except Exception as e:
            logger.error(f"Ошибка в check_channels: {e}")

    async def periodic_check(self):
        check_count = 0
        while self.is_running:
            try:
                await self.check_channels()
                check_count += 1

                # Переподключаемся каждые 10 проверок
                if check_count >= 10:
                    if self.client and self.client.is_connected():
                        await self.client.disconnect()
                    self.is_connected = False
                    check_count = 0
                    logger.info("Переподключаемся для обновления сессии")

                logger.info(f"Ожидаем {CHECK_INTERVAL} секунд до следующей проверки...")
                await asyncio.sleep(CHECK_INTERVAL)

            except Exception as e:
                logger.error(f"Ошибка в periodic_check: {e}")
                self.is_connected = False
                await asyncio.sleep(60)


async def run_monitor():
    """Запускает монитор из основного бота"""
    monitor_instance = ChannelMonitor()
    await monitor_instance.start()

    try:
        # Бесконечный цикл для поддержания работы
        while True:
            await asyncio.sleep(60)
    except KeyboardInterrupt:
        await monitor_instance.stop()
    except Exception as e:
        logger.error(f"Ошибка в run_monitor: {e}")
        await monitor_instance.stop()


# Глобальный экземпляр монитора
monitor = ChannelMonitor()


async def start_monitor():
    await monitor.start()


async def stop_monitor():
    await monitor.stop()