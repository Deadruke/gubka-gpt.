
import os
import asyncio
import base64
import json
import re
from urllib.parse import quote

from aiohttp import web, ClientSession, ClientTimeout
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

# =========================
# НАСТРОЙКИ
# =========================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")

GITHUB_REPO = os.getenv("GITHUB_REPO", "Deadruke/gubka-gpt.")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

if not all([
    TELEGRAM_TOKEN,
    OPENROUTER_KEY,
    GITHUB_TOKEN,
    ALLOWED_USER_ID
]):
    raise RuntimeError(
        "Не настроены обязательные Environment Variables"
    )

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Подготовленные, но ещё не сохранённые изменения
pending_changes = {}

# История обычного чата
chat_history = {}

# Защита от одновременных запросов
user_locks = {}


# =========================
# ОБЩИЕ ФУНКЦИИ
# =========================

def allowed(message):
    return (
        message.from_user is not None
        and str(message.from_user.id) == ALLOWED_USER_ID
    )


def get_lock(user_id):
    if user_id not in user_locks:
        user_locks[user_id] = asyncio.Lock()
    return user_locks[user_id]


def safe_path(path):
    path = path.strip().strip("/")
    parts = path.split("/")

    if not path or any(
        part in ("", ".", "..") for part in parts
    ):
        raise ValueError("Некорректный путь")

    forbidden = (
        ".env",
        ".git",
        "__pycache__"
    )

    if any(
        path == item or path.startswith(item + "/")
        for item in forbidden
    ):
        raise ValueError("Этот путь запрещён")

    return path


async def send_long(message, text):
    for start in range(0, len(text), 3900):
        await message.answer(text[start:start + 3900])


# =========================
# GITHUB
# =========================

async def github_request(method, path="", payload=None):
    url = f"https://api.github.com/repos/{GITHUB_REPO}"

    if path:
        url += "/" + quote(path, safe="/")

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    timeout = ClientTimeout(total=40)

    async with ClientSession(timeout=timeout) as session:
        async with session.request(
            method,
            url,
            headers=headers,
            json=payload,
            params=(
                {"ref": GITHUB_BRANCH}
                if method == "GET" and path.startswith("contents")
                else None
            )
        ) as response:

            result = await response.json(content_type=None)

            if response.status >= 400:
                error = result.get(
                    "message",
                    "Неизвестная ошибка"
                )

                raise RuntimeError(
                    f"GitHub API ({response.status}): {error}"
                )

            return result


async def read_github_file(path):
    path = safe_path(path)

    result = await github_request(
        "GET",
        f"contents/{path}"
    )

    if result.get("type") != "file":
        raise RuntimeError("Это не файл")

    content = base64.b64decode(
        result["content"]
    ).decode("utf-8", errors="replace")

    return content, result["sha"]


async def get_project_context():
    root = await github_request("GET", "contents")

    if not isinstance(root, list):
        raise RuntimeError("Не удалось получить список файлов")

    important_files = [
        "main.py",
        "requirements.txt",
        "render.yaml",
        "README.md"
    ]

    root_names = {
        item["name"]
        for item in root
        if item.get("type") == "file"
    }

    context = []

    for name in important_files:
        if name not in root_names:
            continue

        try:
            content, _ = await read_github_file(name)

            context.append(
                f"\n===== ФАЙЛ: {name} =====\n"
                f"{content[:16000]}"
            )

        except Exception as error:
            context.append(
                f"\nНе удалось прочитать {name}: {error}"
            )

    if not context:
        raise RuntimeError("Файлы проекта не найдены")

    return "\n".join(context)


async def save_file(path, content):
    path = safe_path(path)

    payload = {
        "message": f"Update {path}",
        "content": base64.b64encode(
            content.encode("utf-8")
        ).decode("ascii"),
        "branch": GITHUB_BRANCH
    }

    try:
        _, sha = await read_github_file(path)
        payload["sha"] = sha

    except RuntimeError as error:
        if "404" not in str(error):
            raise

    return await github_request(
        "PUT",
        f"contents/{path}",
        payload
    )


# =========================
# OPENROUTER / ИИ
# =========================

async def ask_ai(system_prompt, user_prompt):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        "max_tokens": 10000
    }

    timeout = ClientTimeout(total=120)

    async with ClientSession(timeout=timeout) as session:
        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data
        ) as response:

            result = await response.json(
                content_type=None
            )

            if response.status != 200:
                raise RuntimeError(
                    f"OpenRouter ({response.status}): "
                    f"{str(result)[:1000]}"
                )

            choices = result.get("choices", [])

            if not choices:
                raise RuntimeError("ИИ не вернул ответ")

            content = choices[0]["message"].get("content")

            if not isinstance(content, str) or not content.strip():
                raise RuntimeError("ИИ вернул пустой ответ")

            return content.strip()


# =========================
# ОБЫЧНЫЙ ЧАТ
# =========================

CHAT_SYSTEM = """
Ты — Губка GPT, личный ИИ-помощник пользователя.

Общайся на русском языке.
Отвечай естественно, понятно и по делу.
Помогай с вопросами, идеями, обучением и программированием.

ВАЖНО:
Обычный чат — это только разговор.
Не пытайся менять файлы GitHub.
Не утверждай, что ты выполнил действия, которые не выполнял.
Если пользователь хочет изменить проект, предложи использовать команду /code.
"""


async def chat_with_ai(user_id, text):
    history = chat_history.setdefault(user_id, [])

    messages = [
        {
            "role": "system",
            "content": CHAT_SYSTEM
        }
    ]

    messages.extend(history[-10:])

    messages.append({
        "role": "user",
        "content": text
    })

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 2000
    }

    timeout = ClientTimeout(total=90)

    async with ClientSession(timeout=timeout) as session:
        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data
        ) as response:

            result = await response.json(
                content_type=None
            )

            if response.status != 200:
                raise RuntimeError(
                    f"OpenRouter ({response.status}): "
                    f"{str(result)[:800]}"
                )

            choices = result.get("choices", [])

            if not choices:
                raise RuntimeError("ИИ не вернул ответ")

            answer = choices[0]["message"].get("content")

            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError("Получен пустой ответ")

    history.append({
        "role": "user",
        "content": text
    })

    history.append({
        "role": "assistant",
        "content": answer
    })

    chat_history[user_id] = history[-20:]

    return answer.strip()


# =========================
# ИИ-РАЗРАБОТЧИК
# =========================

CODE_SYSTEM = """
Ты — Губка GPT, ИИ-разработчик существующего Python-проекта.

Тебе переданы задача пользователя и текущие файлы проекта.

ТВОЯ ГЛАВНАЯ ЦЕЛЬ:
Выполнить именно задачу пользователя.
Не подменяй её другими улучшениями.

ПРАВИЛА:
1. Сначала внимательно изучи текущий код.
2. Не меняй функции, не связанные с задачей.
3. Сохраняй существующие возможности проекта.
4. Возвращай полный новый текст каждого изменяемого файла.
5. Не используй сокращения вроде "... остальной код без изменений".
6. Не придумывай результаты тестов.
7. Не раскрывай секреты и токены.
8. Не добавляй секреты в файлы.
9. Не изменяй .env, .git и секретные файлы.
10. Не удаляй файлы.
11. Не более пяти изменяемых файлов.
12. Если задача уже выполнена, верни пустой files.
13. Если не хватает информации, объясни это в summary и верни пустой files.
14. Не добавляй приветствия и другие несвязанные функции.
15. Если задача касается команды Telegram, проверь совместимость с существующей архитектурой aiogram.

Верни только JSON такого формата:

{
  "summary": "Кратко и точно, что сделано для задачи пользователя",
  "files": [
    {
      "path": "main.py",
      "content": "Полный текст нового файла"
    }
  ]
}

Никакого Markdown вокруг JSON.
"""


def extract_json(answer):
    answer = answer.strip()

    answer = re.sub(
        r"^```(?:json)?\s*",
        "",
        answer
    )

    answer = re.sub(
        r"\s*```$",
        "",
        answer
    )

    start = answer.find("{")

    if start == -1:
        raise ValueError("В ответе ИИ нет JSON")

    result, _ = json.JSONDecoder().raw_decode(
        answer[start:]
    )

    return result


async def prepare_changes(task):
    project = await get_project_context()

    user_prompt = (
        "ЗАДАЧА ПОЛЬЗОВАТЕЛЯ:\n"
        f"{task}\n\n"
        "ТЕКУЩИЙ КОД ПРОЕКТА:\n"
        f"{project}\n\n"
        "Выполни только указанную задачу. "
        "Верни полный текст изменённых файлов."
    )

    answer = await ask_ai(
        CODE_SYSTEM,
        user_prompt
    )

    result = extract_json(answer)

    summary = result.get("summary")
    files = result.get("files")

    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("ИИ не объяснил подготовленные изменения")

    if not isinstance(files, list) or len(files) > 5:
        raise ValueError("ИИ вернул неправильный список файлов")

    checked = []
    used_paths = set()

    for item in files:
        if not isinstance(item, dict):
            raise ValueError("Некорректный формат файла")

        path = safe_path(str(item.get("path", "")))

        if path in used_paths:
            raise ValueError(f"Повторяется файл: {path}")

        used_paths.add(path)

        content = item.get("content")

        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"Пустое содержимое файла: {path}")

        if len(content.encode("utf-8")) > 50000:
            raise ValueError(f"Файл слишком большой: {path}")

        checked.append({
            "path": path,
            "content": content
        })

    return summary.strip(), checked


# =========================
# TELEGRAM: КОМАНДЫ
# =========================

@dp.message(Command("start"))
async def start(message: Message):
    if not allowed(message):
        return

    await message.answer(
        "Привет! Я Губка GPT.\n\n"
        "Я могу общаться с тобой и помогать "
        "работать над твоим GitHub-проектом.\n\n"
        "Обычные сообщения — для общения.\n"
        "/code — изменить проект.\n"
        "/help — все команды."
    )


@dp.message(Command("help"))
async def help_command(message: Message):
    if not allowed(message):
        return

    await message.answer(
        "КОМАНДЫ ГУБКИ GPT\n\n"
        "/start — приветствие\n"
        "/status — состояние бота и GitHub\n"
        "/repo — информация о репозитории\n"
        "/ls — список файлов\n"
        "/ls папка — содержимое папки\n"
        "/read main.py — прочитать файл\n"
        "/write файл.py текст — записать файл\n"
        "/code задача — поручить ИИ изменить проект\n"
        "/apply — подтвердить изменения\n"
        "/cancel — отменить изменения\n"
        "/reset — очистить историю чата\n\n"
        "Просто отправляй сообщения, чтобы общаться со мной."
    )


@dp.message(Command("status"))
async def status(message: Message):
    if not allowed(message):
        return

    await message.answer("Проверяю состояние...")

    try:
        repo = await github_request("GET")

        await message.answer(
            "СОСТОЯНИЕ ГУБКИ GPT\n\n"
            "Бот: работает\n"
            "ИИ: настроен\n"
            "GitHub: подключён\n"
            f"Репозиторий: {repo['full_name']}\n"
            f"Ветка: {GITHUB_BRANCH}\n"
            f"Модель: {MODEL}\n"
            f"Ожидают подтверждения: "
            f"{'да' if message.from_user.id in pending_changes else 'нет'}"
        )

    except Exception as error:
        await message.answer(
            f"Бот работает, но проверка GitHub не прошла:\n{error}"
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

    except Exception as error:
        await message.answer(f"Ошибка: {error}")


@dp.message(Command("ls"))
async def ls(message: Message):
    if not allowed(message):
        return

    try:
        args = (message.text or "").split(maxsplit=1)

        path = (
            "contents/" + safe_path(args[1])
            if len(args) > 1
            else "contents"
        )

        data = await github_request("GET", path)

        if isinstance(data, dict):
            data = [data]

        lines = []

        for item in data:
            icon = "📁" if item.get("type") == "dir" else "📄"
            lines.append(
                f"{icon} {item.get('name', 'Без имени')}"
            )

        await message.answer(
            "\n".join(lines) or "Папка пустая"
        )

    except Exception as error:
        await message.answer(f"Ошибка: {error}")


@dp.message(Command("read"))
async def read(message: Message):
    if not allowed(message):
        return

    args = (message.text or "").split(maxsplit=1)

    if len(args) < 2:
        await message.answer("Напиши: /read main.py")
        return

    try:
        content, _ = await read_github_file(args[1])

        await send_long(
            message,
            f"Файл: {args[1]}\n\n{content}"
        )

    except Exception as error:
        await message.answer(f"Ошибка: {error}")


@dp.message(Command("write"))
async def write(message: Message):
    if not allowed(message):
        return

    parts = (message.text or "").split(maxsplit=2)

    if len(parts) < 3:
        await message.answer(
            "Формат:\n"
            "/write test.py\n"
            "print('Hello world')"
        )
        return

    try:
        path = safe_path(parts[1])

        await save_file(path, parts[2])

        await message.answer(
            f"Файл {path} записан в GitHub."
        )

    except Exception as error:
        await message.answer(f"Ошибка: {error}")


# =========================
# TELEGRAM: РЕЖИМ РАЗРАБОТЧИКА
# =========================

@dp.message(Command("code"))
async def code_command(message: Message):
    if not allowed(message):
        return

    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Напиши задачу после команды.\n\n"
            "Например:\n"
            "/code Добавь команду /status"
        )
        return

    task = parts[1].strip()
    user_id = message.from_user.id

    async with get_lock(user_id):
        await message.answer(
            "Изучаю проект и готовлю изменения под твою задачу..."
        )

        try:
            summary, files = await prepare_changes(task)

            if not files:
                await message.answer(
                    f"Изменения не подготовлены.\n\n{summary}"
                )
                return

            pending_changes[user_id] = {
                "task": task,
                "summary": summary,
                "files": files
            }

            preview = (
                "ПОДГОТОВЛЕНЫ ИЗМЕНЕНИЯ\n\n"
                f"Твоя задача:\n{task}\n\n"
                f"Что подготовлено:\n{summary}\n\n"
                "Файлы:\n"
            )

            for item in files:
                lines = item["content"].count("\n") + 1

                preview += (
                    f"📄 {item['path']} "
                    f"({lines} строк)\n"
                )

            preview += (
                "\nПока ничего не записано в GitHub.\n"
                "Проверь описание.\n\n"
                "/apply — сохранить изменения\n"
                "/cancel — отменить"
            )

            await message.answer(preview)

        except Exception as error:
            await message.answer(
                f"Не удалось подготовить изменения:\n"
                f"{str(error)[:1500]}"
            )


@dp.message(Command("apply"))
async def apply(message: Message):
    if not allowed(message):
        return

    user_id = message.from_user.id

    async with get_lock(user_id):
        changes = pending_changes.get(user_id)

        if not changes:
            await message.answer(
                "Нет изменений для подтверждения."
            )
            return

        await message.answer(
            "Отправляю подготовленные файлы в GitHub..."
        )

        try:
            saved = []

            for item in changes["files"]:
                await save_file(
                    item["path"],
                    item["content"]
                )

                saved.append(item["path"])

            del pending_changes[user_id]

            await message.answer(
                "Изменения сохранены в GitHub!\n\n"
                + "\n".join(f"📄 {path}" for path in saved)
                + "\n\nRender должен начать новый деплой."
            )

        except Exception as error:
            await message.answer(
                "Ошибка при сохранении:\n"
                f"{str(error)[:1200]}\n\n"
                "Если часть файлов уже сохранилась, "
                "проверь GitHub перед повторной попыткой."
            )


@dp.message(Command("cancel"))
async def cancel(message: Message):
    if not allowed(message):
        return

    pending_changes.pop(message.from_user.id, None)

    await message.answer(
        "Подготовленные изменения отменены. "
        "В GitHub ничего не отправлено."
    )


@dp.message(Command("reset"))
async def reset(message: Message):
    if not allowed(message):
        return

    chat_history.pop(message.from_user.id, None)

    await message.answer(
        "История обычного чата очищена."
    )


# =========================
# TELEGRAM: ОБЫЧНЫЙ ЧАТ
# =========================

@dp.message()
async def ordinary_chat(message: Message):
    if not allowed(message):
        return

    text = (message.text or "").strip()

    if not text:
        return

    if text.startswith("/"):
        await message.answer(
            "Неизвестная команда. Напиши /help."
        )
        return

    user_id = message.from_user.id

    async with get_lock(user_id):
        await message.answer("Думаю...")

        try:
            answer = await chat_with_ai(
                user_id,
                text
            )

            await send_long(message, answer)

        except Exception as error:
            await message.answer(
                f"Не получилось получить ответ:\n"
                f"{str(error)[:1200]}"
            )


# =========================
# ЗАПУСК
# =========================

async def main():
    app = web.Application()

    app.router.add_get(
        "/",
        lambda request: web.Response(
            text="Губка GPT работает!"
        )
    )

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", 10000))

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    print("Губка GPT запущен!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
