"""
Start handler - main menu and navigation
"""
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart, CommandHelp

from config import Config

router = Router(name="start")


class MenuStates(StatesGroup):
    """States for menu navigation"""
    waiting_for_main_menu = State()
    waiting_for_video_upload = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command"""
    await state.clear()
    
    welcome_text = (
        f"🎬 <b>REELFIX</b> - Профессиональный бот для обработки видео\n\n"
        f"✨ <b>Возможности:</b>\n"
        f"• Автоматические субтитры с 5 стилями\n"
        f"• Распознавание речи (Whisper)\n"
        f"• AI-улучшение качества видео\n"
        f"• Улучшение звука\n"
        f"• Удаление пауз\n"
        f"• Обрезка и изменение формата\n"
        f"• Цветокоррекция\n"
        f"• Добавление музыки\n\n"
        f"🚀 <b>Выберите действие:</b>"
    )
    
    keyboard = [
        [
            {"text": "📹 Загрузить видео", "callback_data": "upload_video"},
            {"text": "📝 Субтитры", "callback_data": "subtitles_menu"}
        ],
        [
            {"text": "✨ Улучшить качество", "callback_data": "enhance_quality"},
            {"text": "🎵 Аудио", "callback_data": "audio_menu"}
        ],
        [
            {"text": "✂️ Обрезать видео", "callback_data": "trim_video"},
            {"text": "🎨 Цветокоррекция", "callback_data": "color_correction"}
        ],
        [
            {"text": "🎵 Добавить музыку", "callback_data": "add_music"},
            {"text": "❓ Помощь", "callback_data": "help"}
        ]
    ]
    
    await message.answer(welcome_text, reply_markup=keyboard)
    await state.set_state(MenuStates.waiting_for_main_menu)


@router.message(CommandHelp())
async def cmd_help(message: Message):
    """Handle /help command"""
    help_text = (
        "<b>📚 Справка по REELFIX</b>\n\n"
        "<b>Основные команды:</b>\n"
        "/start - Главное меню\n"
        "/help - Эта справка\n\n"
        "<b>Функции бота:</b>\n"
        "1. <b>Субтитры</b> - Автоматическое распознавание речи с выбором стилей\n"
        "2. <b>Улучшение качества</b> - AI-апскейлинг, шумоподавление, резкость\n"
        "3. <b>Аудио</b> - Нормализация, шумоподавление\n"
        "4. <b>Обрезка</b> - Удаление пауз, изменение формата\n"
        "5. <b>Цветокоррекция</b> - Настройка цветов, контраста\n"
        "6. <b>Музыка</b> - Добавление фоновой музыки\n\n"
        "<b>Поддерживаемые форматы:</b> MP4, WebM, MOV, AVI, MKV\n"
        "<b>Максимальный размер:</b> 500 MB"
    )
    
    keyboard = [
        [{"text": "🏠 Главное меню", "callback_data": "start_menu"}]
    ]
    
    await message.answer(help_text, reply_markup=keyboard)


@router.callback_query(F.data == "start_menu")
async def start_menu(callback: Message):
    """Return to main menu"""
    welcome_text = (
        f"🎬 <b>REELFIX</b> - Профессиональный бот для обработки видео\n\n"
        f"🚀 <b>Выберите действие:</b>"
    )
    
    keyboard = [
        [
            {"text": "📹 Загрузить видео", "callback_data": "upload_video"},
            {"text": "📝 Субтитры", "callback_data": "subtitles_menu"}
        ],
        [
            {"text": "✨ Улучшить качество", "callback_data": "enhance_quality"},
            {"text": "🎵 Аудио", "callback_data": "audio_menu"}
        ],
        [
            {"text": "✂️ Обрезать видео", "callback_data": "trim_video"},
            {"text": "🎨 Цветокоррекция", "callback_data": "color_correction"}
        ],
        [
            {"text": "🎵 Добавить музыку", "callback_data": "add_music"},
            {"text": "❓ Помощь", "callback_data": "help"}
        ]
    ]
    
    await callback.message.edit_text(welcome_text, reply_markup=keyboard)


@router.callback_query(F.data == "help")
async def show_help(callback: Message):
    """Show help message"""
    help_text = (
        "<b>📚 Справка по REELFIX</b>\n\n"
        "<b>Основные команды:</b>\n"
        "/start - Главное меню\n"
        "/help - Эта справка\n\n"
        "<b>Функции бота:</b>\n"
        "1. <b>Субтитры</b> - Автоматическое распознавание речи с выбором стилей\n"
        "2. <b>Улучшение качества</b> - AI-апскейлинг, шумоподавление, резкость\n"
        "3. <b>Аудио</b> - Нормализация, шумоподавление\n"
        "4. <b>Обрезка</b> - Удаление пауз, изменение формата\n"
        "5. <b>Цветокоррекция</b> - Настройка цветов, контраста\n"
        "6. <b>Музыка</b> - Добавление фоновой музыки\n\n"
        "<b>Поддерживаемые форматы:</b> MP4, WebM, MOV, AVI, MKV\n"
        "<b>Максимальный размер:</b> 500 MB"
    )
    
    keyboard = [
        [{"text": "🏠 Главное меню", "callback_data": "start_menu"}]
    ]
    
    await callback.message.edit_text(help_text, reply_markup=keyboard)


@router.callback_query(F.data == "upload_video")
async def upload_video(callback: Message):
    """Upload video handler"""
    upload_text = (
        "📹 <b>Загрузка видео</b>\n\n"
        "Пожалуйста, отправьте видео файл. "
        "Поддерживаемые форматы: MP4, WebM, MOV, AVI, MKV\n"
        "Максимальный размер: 500 MB"
    )
    
    keyboard = [
        [{"text": "🏠 Главное меню", "callback_data": "start_menu"}]
    ]
    
    await callback.message.edit_text(upload_text, reply_markup=keyboard)


@router.callback_query(F.data == "subtitles_menu")
async def subtitles_menu(callback: Message):
    """Subtitles menu"""
    subtitles_text = (
        "📝 <b>Автоматические субтитры</b>\n\n"
        "Выберите стиль субтитров для распознавания речи:\n\n"
        "1. <b>Классический</b> - Чёрный обвод, полупрозрачный фон\n"
        "2. <b>Модерн</b> - Зелёный цвет, без обводки\n"
        "3. <b>Минимал</b> - Минималистичный стиль\n"
        "4. <b>Жирный</b> - Жёлтый цвет, жирный шрифт\n"
        "5. <b>Элегант</b> - Красный цвет, полупрозрачный фон"
    )
    
    keyboard = [
        [
            {"text": "1️⃣ Классический", "callback_data": "subtitle_classic"},
            {"text": "2️⃣ Модерн", "callback_data": "subtitle_modern"}
        ],
        [
            {"text": "3️⃣ Минимал", "callback_data": "subtitle_minimal"},
            {"text": "4️⃣ Жирный", "callback_data": "subtitle_bold"}
        ],
        [
            {"text": "5️⃣ Элегант", "callback_data": "subtitle_elegant"},
            {"text": "🏠 Главное меню", "callback_data": "start_menu"}
        ]
    ]
    
    await callback.message.edit_text(subtitles_text, reply_markup=keyboard)


@router.callback_query(F.data == "enhance_quality")
async def enhance_quality(callback: Message):
    """Enhance quality menu"""
    quality_text = (
        "✨ <b>Улучшение качества видео</b>\n\n"
        "Выберите опции улучшения:\n\n"
        "• <b>AI-апскейлинг</b> - Увеличение разрешения (2x)\n"
        "• <b>Шумоподавление</b> - Удаление цифрового шума\n"
        "• <b>Резкость</b> - Улучшение чёткости\n"
        "• <b>Все вместе</b> - Полное улучшение"
    )
    
    keyboard = [
        [
            {"text": "🔹 Только апскейлинг", "callback_data": "enhance_upscale"},
            {"text": "🔹 Только шумоподавление", "callback_data": "enhance_denoise"}
        ],
        [
            {"text": "🔹 Только резкость", "callback_data": "enhance_sharpen"},
            {"text": "🔹 Все вместе", "callback_data": "enhance_all"}
        ],
        [
            {"text": "🏠 Главное меню", "callback_data": "start_menu"}
        ]
    ]
    
    await callback.message.edit_text(quality_text, reply_markup=keyboard)


@router.callback_query(F.data == "audio_menu")
async def audio_menu(callback: Message):
    """Audio menu"""
    audio_text = (
        "🎵 <b>Улучшение звука</b>\n\n"
        "Выберите опции улучшения аудио:\n\n"
        "• <b>Нормализация</b> - Выравнивание громкости\n"
        "• <b>Шумоподавление</b> - Удаление фонового шума\n"
        "• <b>Компрессия</b> - Баланс громкости\n"
        "• <b>Все вместе</b> - Полное улучшение"
    )
    
    keyboard = [
        [
            {"text": "🔹 Только нормализация", "callback_data": "audio_normalize"},
            {"text": "🔹 Только шумоподавление", "callback_data": "audio_denoise"}
        ],
        [
            {"text": "🔹 Компрессия", "callback_data": "audio_compression"},
            {"text": "🔹 Все вместе", "callback_data": "audio_all"}
        ],
        [
            {"text": "🏠 Главное меню", "callback_data": "start_menu"}
        ]
    ]
    
    await callback.message.edit_text(audio_text, reply_markup=keyboard)


@router.callback_query(F.data == "trim_video")
async def trim_video(callback: Message):
    """Trim video menu"""
    trim_text = (
        "✂️ <b>Обрезка видео</b>\n\n"
        "Выберите действие:\n\n"
        "• <b>Удалить паузы</b> - Автоматическое удаление пауз и тишины\n"
        "• <b>Обрезать по времени</b> - Указать начало и конец\n"
        "• <b>Изменить формат</b> - Конвертация в другой формат\n"
        "• <b>Удалить чёрные полосы</b> - Автообрезка краёв"
    )
    
    keyboard = [
        [
            {"text": "🔹 Удалить паузы", "callback_data": "trim_remove_pause"},
            {"text": "🔹 Обрезать по времени", "callback_data": "trim_by_time"}
        ],
        [
            {"text": "🔹 Изменить формат", "callback_data": "trim_format"},
            {"text": "🔹 Удалить полосы", "callback_data": "trim_crop"}
        ],
        [
            {"text": "🏠 Главное меню", "callback_data": "start_menu"}
        ]
    ]
    
    await callback.message.edit_text(trim_text, reply_markup=keyboard)


@router.callback_query(F.data == "color_correction")
async def color_correction(callback: Message):
    """Color correction menu"""
    color_text = (
        "🎨 <b>Цветокоррекция</b>\n\n"
        "Выберите опции:\n\n"
        "• <b>Авто-баланс</b> - Баланс цветов\n"
        "• <b>Контраст</b> - Улучшение контраста\n"
        "• <b>Яркость</b> - Регулировка яркости\n"
        "• <b>Насыщенность</b> - Усиление цветов\n"
        "• <b>Все вместе</b> - Полная цветокоррекция"
    )
    
    keyboard = [
        [
            {"text": "🔹 Авто-баланс", "callback_data": "color_auto"},
            {"text": "🔹 Контраст", "callback_data": "color_contrast"}
        ],
        [
            {"text": "🔹 Яркость", "callback_data": "color_brightness"},
            {"text": "🔹 Насыщенность", "callback_data": "color_saturation"}
        ],
        [
            {"text": "🔹 Все вместе", "callback_data": "color_all"},
            {"text": "🏠 Главное меню", "callback_data": "start_menu"}
        ]
    ]
    
    await callback.message.edit_text(color_text, reply_markup=keyboard)


@router.callback_query(F.data == "add_music")
async def add_music(callback: Message):
    """Add music menu"""
    music_text = (
        "🎵 <b>Добавление музыки</b>\n\n"
        "Выберите действие:\n\n"
        "• <b>Добавить музыку</b> - Загрузить фоновой трек\n"
        "• <b>Настроить громкость</b> - Регулировка громкости музыки\n"
        "• <b>Настроить громкость видео</b> - Баланс видео и музыки\n"
        "• <b>Объединить видео и музыку</b> - Создать финальный файл"
    )
    
    keyboard = [
        [
            {"text": "🔹 Добавить музыку", "callback_data": "music_add"},
            {"text": "🔹 Настроить громкость", "callback_data": "music_volume"}
        ],
        [
            {"text": "🔹 Баланс громкости", "callback_data": "music_balance"},
            {"text": "🔹 Объединить", "callback_data": "music_merge"}
        ],
        [
            {"text": "🏠 Главное меню", "callback_data": "start_menu"}
        ]
    ]
    
    await callback.message.edit_text(music_text, reply_markup=keyboard)