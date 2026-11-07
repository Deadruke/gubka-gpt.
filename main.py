import os
import asyncio
from aiohttp import web, ClientSession
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()


async def ask_ai(prompt):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}]
    }

    async with ClientSession() as session:
        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data
        ) as response:
            result = await response.json()

            if response.status != 200:
                return f"Ошибка AI: {result}"

            return result["choices"][0]["message"]["content"]


@dp.message(Command("start"))
async def start(message: Message):
    if ALLOWED_USER_ID and str(message.from_user.id) != ALLOWED_USER_ID:
        return

    await message.answer(
        "Привет! Я Губка GPT.\n"
        "Можешь задавать вопросы или просить меня писать код."
    )


@dp.message()
async def chat(message: Message):
    if ALLOWED_USER_ID and str(message.from_user.id) != ALLOWED_USER_ID:
        return

    if not OPENROUTER_KEY:
        await message.answer("Не настроен OPENROUTER_API_KEY.")
        return

    await bot.send_chat_action(message.chat.id, "typing")

    try:
        answer = await ask_ai(message.text or "")
        await message.answer(answer[:4000])
    except Exception as error:
        await message.answer(f"Ошибка: {error}")


async def health(request):
    return web.Response(text="Gubka GPT is running!")


async def main():
    app = web.Application()
    app.router.add_get("/", health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")

    asyncio.run(main())
