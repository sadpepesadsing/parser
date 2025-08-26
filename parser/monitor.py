# monitor.py
import asyncio
from telethon import TelegramClient, errors
from telethon.tl.types import Message, MessageMediaPhoto, Channel, Chat
from config import API_ID, API_HASH, CHECK_INTERVAL, PHONE_NUMBER
from database.db import (
    get_all_monitor_channels, get_last_post_id, update_last_post_id, 
    get_users_monitoring_channel, set_channel_subscribed, is_channel_subscribed,
    get_channels_to_subscribe
)
from bot import bot
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChannelMonitor:
    def __init__(self):
        self.client = None
        self.is_running = False
        self.is_connected = False

    async def ensure_connection(self):
        """Убедиться, что соединение установлено"""
        if self.is_connected and self.client and self.client.is_connected():
            return True
        
        try:
            if self.client:
                await self.client.disconnect()
            
            self.client = TelegramClient('user_session', API_ID, API_HASH)
            await self.client.start(phone=PHONE_NUMBER)
            self.is_connected = True
            logger.info("Соединение с Telegram установлено")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка подключения: {e}")
            self.is_connected = False
            return False

    async def start(self):
        """Запуск монитора"""
        self.is_running = True
        logger.info("Монитор каналов запущен")
        
        # Устанавливаем соединение
        if await self.ensure_connection():
            # Подписываемся на необходимые каналы
            await self.subscribe_to_channels()
        
        # Запускаем периодическую проверку
        asyncio.create_task(self.periodic_check())

    async def stop(self):
        """Остановка монитора"""
        self.is_running = False
        if self.client and self.client.is_connected():
            await self.client.disconnect()
        self.is_connected = False
        logger.info("Монитор каналов остановлен")

    async def subscribe_to_channels(self):
        """Подписаться на все необходимые каналы"""
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
                    
                    await asyncio.sleep(3)  # Пауза между подписками
                    
                except Exception as e:
                    logger.error(f"Ошибка подписки на {channel_username}: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка в subscribe_to_channels: {e}")

    async def subscribe_to_channel(self, channel_username: str) -> bool:
        """Подписаться на конкретный канал"""
        try:
            if not await self.ensure_connection():
                logger.error("Нет соединения для подписки")
                return False
                
            if channel_username.startswith('@'):
                channel_username = channel_username[1:]
            
            # Пробуем найти канал
            try:
                entity = await self.client.get_entity(channel_username)
            except errors.UsernameInvalidError:
                logger.error(f"Неверное имя пользователя: {channel_username}")
                return False
            except errors.UsernameNotOccupiedError:
                logger.error(f"Канал не существует: {channel_username}")
                return False
            
            # Подписываемся на канал
            try:
                await self.client.join_channel(entity)
                await asyncio.sleep(2)  # Даем время для обработки
                return True
                
            except errors.InviteRequestSentError:
                logger.warning(f"Запрос на вступление отправлен для {channel_username}")
                return True  # Считаем успехом, ждем подтверждения
            except errors.UserAlreadyParticipantError:
                logger.info(f"Уже подписан на {channel_username}")
                return True
            except Exception as e:
                logger.error(f"Ошибка join_channel для {channel_username}: {e}")
                return False
            
        except Exception as e:
            logger.error(f"Общая ошибка подписки на {channel_username}: {e}")
            return False

    async def get_channel_entity(self, channel_username):
        """Получить entity канала"""
        try:
            if not await self.ensure_connection():
                return None
                
            if channel_username.startswith('@'):
                channel_username = channel_username[1:]
                
            entity = await self.client.get_entity(channel_username)
            return entity
            
        except Exception as e:
            logger.error(f"Ошибка получения канала {channel_username}: {e}")
            return None

    async def get_new_posts(self, channel_username):
        """Получить новые посты из канала"""
        try:
            if not await self.ensure_connection():
                return []

            # Проверяем, подписан ли уже на канал
            if not await is_channel_subscribed(channel_username):
                logger.info(f"Пытаемся подписаться на {channel_username}")
                success = await self.subscribe_to_channel(channel_username)
                if success:
                    await set_channel_subscribed(channel_username, True)
                else:
                    return []

            entity = await self.get_channel_entity(channel_username)
            if not entity:
                return []

            last_post_id = await get_last_post_id(channel_username)
            messages = []
            
            async for message in self.client.iter_messages(entity, limit=5):
                if message.id > last_post_id and (message.message or message.media):
                    messages.append(message)
                else:
                    break

            if messages:
                # Обновляем последний ID поста
                latest_id = max(msg.id for msg in messages)
                await update_last_post_id(channel_username, latest_id)
                logger.info(f"Найдено {len(messages)} новых постов в {channel_username}")

            return messages

        except Exception as e:
            logger.error(f"Ошибка получения постов из {channel_username}: {e}")
            return []

    async def process_message(self, message, monitor_channel):
        """Обработать сообщение и отправить уведомления"""
        try:
            # Получаем всех пользователей, которые мониторят этот канал
            user_ids = await get_users_monitoring_channel(monitor_channel)
            
            if not user_ids:
                return

            # Формируем текст сообщения
            text = f"📢 **Новый пост в {monitor_channel}:**\n\n"
            if message.message:
                # Обрезаем длинный текст
                if len(message.message) > 1000:
                    text += message.message[:1000] + "..."
                else:
                    text += message.message
            else:
                text += "📷 Фото/медиа"
            
            # Отправляем каждому пользователю
            for user_id in user_ids:
                try:
                    # Если есть медиа, пытаемся отправить с медиа
                    if message.media and hasattr(message.media, 'photo'):
                        await self.send_message_with_media(user_id, text, message)
                    else:
                        # Для текстовых сообщений или других типов медиа
                        await bot.send_message(user_id, text, parse_mode='Markdown')
                        
                except Exception as e:
                    logger.error(f"Ошибка отправки пользователю {user_id}: {e}")

        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")

    async def send_message_with_media(self, user_id, text, message):
        """Отправить сообщение с медиа"""
        try:
            # Скачиваем медиа
            media_data = await message.download_media(file=bytes)
            
            # Отправляем фото с текстом
            await bot.send_photo(
                chat_id=user_id,
                photo=media_data,
                caption=text,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка отправки медиа пользователю {user_id}: {e}")
            # Если не удалось отправить с медиа, отправляем просто текст
            await bot.send_message(user_id, text, parse_mode='Markdown')

    async def check_channels(self):
        """Проверить все каналы на новые посты"""
        try:
            if not await self.ensure_connection():
                logger.warning("Пропускаем проверку - нет соединения")
                return
                
            monitor_channels = await get_all_monitor_channels()
            logger.info(f"Проверяем {len(monitor_channels)} каналов")
            
            for channel in monitor_channels:
                try:
                    new_posts = await self.get_new_posts(channel)
                    for post in reversed(new_posts):  # От старых к новым
                        await self.process_message(post, channel)
                        await asyncio.sleep(1)  # Пауза между постами
                        
                except Exception as e:
                    logger.error(f"Ошибка проверки канала {channel}: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка в check_channels: {e}")

    async def periodic_check(self):
        """Периодическая проверка каналов"""
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
                # При ошибке переподключаемся
                self.is_connected = False
                await asyncio.sleep(60)

# Глобальный экземпляр монитора
monitor = ChannelMonitor()

async def start_monitor():
    """Запустить монитор"""
    await monitor.start()

async def stop_monitor():
    """Остановить монитор"""
    await monitor.stop()
