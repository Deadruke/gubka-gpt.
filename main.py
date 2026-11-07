
import os
import asyncio
import base64
from urllib.parse import quote

from aiohttp import web, ClientSession
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")

GITHUB_REPO = os.getenv("GITHUB_REPO", "Deadruke/gubka-gpt.")
GITHUB_BRANCH = "main"
MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

if not all([TELEGRAM_TOKEN, OPENROUTER_KEY, GITHUB_TOKEN, ALLOWED_USER_ID]):
    raise RuntimeError("Не настроены обязательные Environment Variables")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()


def allowed(message):
    return (
        message.from_user is not None
        and str(message.from_user.id) == ALLOWED_USER_ID
    )


def safe_path(path):
    path = path.strip().strip("/")
    parts = path.split("/")

    if not path or any(p in ("", ".", "..") for p in parts):
        raise ValueError("Некорректный путь к файлу")

    return path


async def github_request(method, path="", payload=None):
    url = f"https://api.github.com/repos/{GITHUB_REPO}"
    if path:
        url += "/" + path

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    async with ClientSession() as session:
        async with session.request(
            method,
            url,
            headers=headers,
            json=payload,
            params={"ref": GITHUB_BRANCH} if method == "GET" else None
        ) as response:
            result = await response.json(content_type=None)

            if response.status >= 400:
                error = result.get("message", "Неизвестная ошибка")
                raise RuntimeError(
                    f"GitHub API ({response.status}): {error}"
                )

            return result


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
                raise RuntimeError(str(result)[:1000])

            return result["choices"][0]["message"]["content"]


@dp.message(Command("start"))
async def start(message: Message):
    if not allowed(message):
        return

    await message.answer(
        "Привет! Я Губка GPT.\n\n"
        "Теперь я умею работать с GitHub.\n"
        "Напиши /help для списка команд."
    )


@dp.message(Command("help"))
async def help_command(message: Message):
    if not allowed(message):
        return

    await message.answer(
        "/repo — информация о репозитории\n"
        "/ls — список файлов\n"
        "/ls папка — содержимое папки\n"
        "/read файл.py — прочитать файл\n"
        "/write файл.py — создать или изменить файл\n\n"
        "Для записи используй формат:\n"
        "/write test.py\n"
        "print('Hello world')"
    )


@dp.message(Command("repo"))
async def repo(message: Message):
    if not allowed(message):
        return

    try:
        data = await github_request("GET")
        await message.answer(
            f"Репозиторий: {data['full_name']}\n"
            f"Ветка: {GITHUB_BRANCH}\n"
            f"Описание: {data.get('description') or 'Нет'}"
        )
    except Exception as e:
        await message.answer(f"Ошибка GitHub: {e}")


@dp.message(Command("ls"))
async def list_files(message: Message):
    if not allowed(message):
        return

    try:
        parts = (message.text or "").split(maxsplit=1)
        folder = safe_path(parts[1]) if len(parts) > 1 else ""

        endpoint = "contents"
        if folder:
            endpoint += "/" + quote(folder, safe="/")

        data = await github_request("GET", endpoint)

        if isinstance(data, dict):
            await message.answer("Это файл, а не папка. Используй /read.")
            return

        lines = [
            ("📁 " if item["type"] == "dir" else "📄 ") + item["name"]
            for item in data
        ]

        await message.answer(
            "\n".join(lines)[:4000] or "Папка пустая."
        )

    except Exception as e:
        await message.answer(f"Ошибка: {e}")


@dp.message(Command("read"))
async def read_file(message: Message):
    if not allowed(message):
        return

    try:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Укажи путь: /read main.py")
            return

        path = safe_path(parts[1])
        data = await github_request(
            "GET", "contents/" + quote(path, safe="/")
        )

        content = base64.b64decode(data["content"]).decode("utf-8")

        if len(content) > 3500:
            content = content[:3500] + "\n... файл обрезан"

        await message.answer(
            f"Файл: {path}\n\n{content}"
        )

    except Exception as e:
        await message.answer(f"Ошибка чтения: {e}")


@dp.message(Command("write"))
async def write_file(message: Message):
    if not allowed(message):
        return

    try:
        text = message.text or ""
        header, separator, content = text.partition("\n")

        parts = header.split(maxsplit=1)

        if len(parts) < 2 or not separator:
            await message.answer(
                "Формат:\n/write test.py\nprint('Hello')"
            )
            return

        path = safe_path(parts[1])

        if len(content.encode("utf-8")) > 20000:
            await message.answer("Файл слишком большой. Максимум 20 КБ.")
            return

        endpoint = "contents/" + quote(path, safe="/")

        existing = None
        try:
            existing = await github_request("GET", endpoint)
        except RuntimeError as e:
            if "404" not in str(e):
                raise

        payload = {
            "message": f"Update {path}",
            "content": base64.b64encode(
                content.encode("utf-8")
            ).decode("ascii"),
            "branch": GITHUB_BRANCH
        }

        if existing:
            payload["sha"] = existing["sha"]

        result = await github_request("PUT", endpoint, payload)

        await message.answer(
            f"Готово! Файл сохранён в GitHub.\n"
            f"Путь: {path}\n"
            f"Коммит: {result['commit']['sha'][:10]}"
        )

    except Exception as e:
        await message.answer(f"Ошибка записи: {e}")


@dp.message()
async def chat(message: Message):
    if not allowed(message):
        return

    if not message.text:
        return

    try:
        await bot.send_chat_action(message.chat.id, "typing")
        answer = await ask_ai(message.text)
        await message.answer(answer[:4000])

    except Exception as e:
        await message.answer(f"Ошибка AI: {e}")


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

    print("Gubka GPT started!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
