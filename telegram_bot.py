"""
CS2 Clip Maker - Telegram Bot
Telegram бот для отправки уведомлений о готовых клипах
"""

import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandHelp
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from datetime import datetime
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем токен из переменных окружения
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

if not BOT_TOKEN:
    logger.warning("TELEGRAM_BOT_TOKEN не установлен. Бот не будет работать.")

# Инициализация бота
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Хранилище пользователей
users = {}


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    """Обработка команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or "неизвестный"
    
    # Сохраняем пользователя
    users[user_id] = {
        "username": username,
        "first_name": message.from_user.first_name,
        "registered_at": datetime.now().isoformat()
    }
    
    # Создаем приветственное сообщение
    welcome_text = (
        f"👋 <b>Здравствуй, @{username}!</b>\n\n"
        f"Я бот для монтажа CS2 клипов.\n\n"
        f"📌 <b>Как это работает:</b>\n"
        f"1. Вставь YouTube ссылку в веб-приложении\n"
        f"2. Я анализирую видео и нахожу интересные моменты\n"
        f"3. Создаю клипы длительностью 60-120 секунд\n"
        f"4. Формат TikTok 9:16, 1080×1920\n"
        f"5. Добавляю субтитры и размытый фон\n\n"
        f"✅ Готовые клипы появятся здесь!"
    )
    
    # Клавиатура с кнопками
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🌐 Открыть веб-приложение",
                url="https://gubka-gpt.onrender.com"
            )
        ],
        [
            InlineKeyboardButton(
                text="❓ Помощь",
                callback_data="help"
            )
        ]
    ])
    
    await message.answer(welcome_text, reply_markup=keyboard)


@dp.message(CommandHelp())
async def cmd_help(message: types.Message):
    """Обработка команды /help"""
    help_text = (
        "<b>🤖 Помощь по боту</b>\n\n"
        "📌 <b>Основные команды:</b>\n"
        "/start - Начать работу\n"
        "/help - Показать эту справку\n\n"
        "📌 <b>Как создавать клипы:</b>\n"
        "1. Открой веб-приложение\n"
        "2. Вставь YouTube ссылку на CS2 видео\n"
        "3. Нажми 'Создать клипы'\n"
        "4. Жди обработки (2-5 минут)\n"
        "5. Скачивай готовые клипы\n\n"
        "📌 <b>Формат клипов:</b>\n"
        "• TikTok 9:16 (1080×1920)\n"
        "• Длительность 60-120 сек\n"
        "• Субтитры и размытый фон\n"
        "• Интересные моменты CS2\n\n"
        "📌 <b>Технологии:</b>\n"
        "• FFmpeg для монтажа\n"
        "• Whisper для субтитров\n"
        "• yt-dlp для скачивания видео\n\n"
        "⏱️ <b>Время обработки:</b>\n"
        "• 1 видео: 2-5 минут\n"
        "• 2-3 клипа: 5-10 минут\n"
        "• 4+ клипа: 10-15 минут"
    )
    
    await message.answer(help_text)


@dp.callback_query(F.data == "help")
async def callback_help(callback: types.CallbackQuery):
    """Обработка callback с кнопкой помощи"""
    help_text = (
        "<b>🤖 Помощь по боту</b>\n\n"
        "📌 <b>Основные команды:</b>\n"
        "/start - Начать работу\n"
        "/help - Показать эту справку\n\n"
        "📌 <b>Как создавать клипы:</b>\n"
        "1. Открой веб-приложение\n"
        "2. Вставь YouTube ссылку на CS2 видео\n"
        "3. Нажми 'Создать клипы'\n"
        "4. Жди обработки (2-5 минут)\n"
        "5. Скачивай готовые клипы\n\n"
        "📌 <b>Формат клипов:</b>\n"
        "• TikTok 9:16 (1080×1920)\n"
        "• Длительность 60-120 сек\n"
        "• Субтитры и размытый фон\n"
        "• Интересные моменты CS2"
    )
    
    await callback.message.edit_text(help_text, reply_markup=None)
    await callback.answer()


@dp.message()
async def handle_message(message: types.Message):
    """Обработка обычных сообщений"""
    user_id = message.from_user.id
    username = message.from_user.username or "неизвестный"
    
    # Проверяем, зарегистрирован ли пользователь
    if user_id not in users:
        users[user_id] = {
            "username": username,
            "first_name": message.from_user.first_name,
            "registered_at": datetime.now().isoformat()
        }
    
    # Обрабатываем текстовые сообщения
    text = message.text.lower()
    
    if "клип" in text or "clip" in text:
        response = (
            f"🎬 <b>Создание клипов</b>\n\n"
            f"Для создания клипов используй веб-приложение:\n"
            f"https://gubka-gpt.onrender.com\n\n"
            f"Вставь YouTube ссылку на CS2 видео и получи готовые клипы!"
        )
    elif "помощь" in text or "help" in text:
        response = (
            "<b>🤖 Помощь по боту</b>\n\n"
            "📌 <b>Основные команды:</b>\n"
            "/start - Начать работу\n"
            "/help - Показать эту справку\n\n"
            "📌 <b>Как создавать клипы:</b>\n"
            "1. Открой веб-приложение\n"
            "2. Вставь YouTube ссылку на CS2 видео\n"
            "3. Нажми 'Создать клипы'\n"
            "4. Жди обработки (2-5 минут)\n"
            "5. Скачивай готовые клипы"
        )
    elif "ссылка" in text or "youtube" in text:
        response = (
            f"🔗 <b>Ссылка на веб-приложение:</b>\n\n"
            f"https://gubka-gpt.onrender.com\n\n"
            f"Там ты можешь вставить YouTube ссылку и создать клипы!"
        )
    else:
        response = (
            f"👋 <b>Привет, @{username}!</b>\n\n"
            f"Я бот для монтажа CS2 клипов.\n\n"
            f"📌 <b>Команды:</b>\n"
            f"/start - Начать работу\n"
            f"/help - Помощь\n\n"
            f"📌 <b>Как создать клип:</b>\n"
            f"1. Открой веб-приложение\n"
            f"2. Вставь YouTube ссылку\n"
            f"3. Нажми 'Создать клипы'\n\n"
            f"✅ Готовые клипы появятся здесь!"
        )
    
    await message.answer(response)


async def notify_user_about_clip(user_id: int, clip_url: str, clip_name: str):
    """Уведомление пользователя о готовом клипе"""
    try:
        if user_id not in users:
            return
        
        username = users[user_id]["username"]
        
        message = (
            f"✅ <b>Клип готов!</b>\n\n"
            f"🎬 <b>{clip_name}</b>\n\n"
            f"Твой CS2 клип готов к скачиванию!\n\n"
            f"🔗 <b>Скачать:</b>\n"
            f"{clip_url}\n\n"
            f"📌 <b>Формат:</b> TikTok 9:16\n"
            f"📌 <b>Длительность:</b> 60-120 сек\n"
            f"📌 <b>Субтитры:</b> Да\n"
            f"📌 <b>Фон:</b> Размытый"
        )
        
        await bot.send_message(
            user_id,
            message,
            parse_mode="HTML"
        )
        
        logger.info(f"Уведомление отправлено пользователю {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")


async def notify_user_about_clips(user_id: int, clips: list):
    """Уведомление пользователя о готовых клипах"""
    try:
        if user_id not in users:
            return
        
        username = users[user_id]["username"]
        
        message = (
            f"✅ <b>Все клипы готовы!</b>\n\n"
            f"👋 <b>Привет, @{username}!</b>\n\n"
            f"Твои CS2 клипы готовы к скачиванию!\n\n"
            f"📹 <b>Готовые клипы:</b>\n"
        )
        
        for i, clip in enumerate(clips, 1):
            message += f"\n{i}. <b>{clip.get('name', 'Клип')}</b>\n"
            message += f"   • Длительность: {clip.get('duration', 'N/A')} сек\n"
            message += f"   • Скачать: {clip.get('url', 'N/A')}\n"
        
        message += (
            f"\n🔗 <b>Веб-приложение:</b>\n"
            f"https://gubka-gpt.onrender.com\n\n"
            f"📌 <b>Формат:</b> TikTok 9:16\n"
            f"📌 <b>Субтитры:</b> Да\n"
            f"📌 <b>Фон:</b> Размытый"
        )
        
        await bot.send_message(
            user_id,
            message,
            parse_mode="HTML"
        )
        
        logger.info(f"Уведомление о клипах отправлено пользователю {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о клипах: {e}")


async def main():
    """Запуск бота"""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен. Бот не запущен.")
        return
    
    logger.info("Запуск Telegram бота...")
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")