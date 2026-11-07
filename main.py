import os
import asyncio
import base64
import re
from urllib.parse import quote

from aiohttp import web, ClientSession, ClientTimeout
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message


# ============================================================
# CONFIGURATION
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")

GITHUB_REPO = os.getenv("GITHUB_REPO", "Deadruke/gubka-gpt.")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

if not all((TELEGRAM_TOKEN, OPENROUTER_KEY, GITHUB_TOKEN, ALLOWED_USER_ID)):
    raise RuntimeError("Не настроены обязательные Environment Variables")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# These dictionaries live in memory. Render restarts clear pending changes/history.
pending_changes = {}
chat_history = {}
user_locks = {}

MAX_FILE_BYTES = 50_000
MAX_CONTEXT_CHARS = 55_000
MAX_FILES_PER_CHANGE = 5


# ============================================================
# GENERAL HELPERS
# ============================================================

def allowed(message: Message) -> bool:
    return (
        message.from_user is not None
        and str(message.from_user.id) == ALLOWED_USER_ID
    )


def get_lock(user_id: int) -> asyncio.Lock:
    if user_id not in user_locks:
        user_locks[user_id] = asyncio.Lock()
    return user_locks[user_id]


def safe_path(path: str) -> str:
    path = (path or "").strip()

    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or ":" in path
        or "{" in path
        or "}" in path
    ):
        raise ValueError("Некорректный путь к файлу")

    path = path.strip("/")
    parts = path.split("/")

    if not path or any(part in ("", ".", "..") for part in parts):
        raise ValueError("Некорректный путь к файлу")

    forbidden = (".env", ".git", "__pycache__")

    if any(
        part in forbidden
        for part in parts
    ):
        raise ValueError("Этот путь запрещён")

    return path


async def send_long(message: Message, text: str):
    # Telegram message limit is 4096 characters. Keep a safety margin.
    for start in range(0, len(text), 3900):
        await message.answer(text[start:start + 3900])


# ============================================================
# GITHUB
# ============================================================

async def github_request(method: str, path: str = "", payload=None):
    url = f"https://api.github.com/repos/{GITHUB_REPO}"

    if path:
        url += "/" + quote(path, safe="/")

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    timeout = ClientTimeout(total=45)

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
            ),
        ) as response:
            result = await response.json(content_type=None)

            if response.status >= 400:
                error = result.get("message", "Неизвестная ошибка")
                raise RuntimeError(
                    f"GitHub API ({response.status}): {error}"
                )

            return result


async def read_github_file(path: str):
    path = safe_path(path)
    result = await github_request("GET", f"contents/{path}")

    if result.get("type") != "file":
        raise RuntimeError(f"{path} — это не файл")

    encoded = result.get("content", "")
    content = base64.b64decode(encoded).decode(
        "utf-8",
        errors="replace",
    )

    return content, result["sha"]


async def get_project_context():
    root = await github_request("GET", "contents")

    if not isinstance(root, list):
        raise RuntimeError("Не удалось получить список файлов репозитория")

    important_files = (
        "main.py",
        "requirements.txt",
        "render.yaml",
        "README.md",
    )

    root_files = {
        item.get("name")
        for item in root
        if item.get("type") == "file"
    }

    sections = []
    total_chars = 0

    for name in important_files:
        if name not in root_files:
            continue

        content, _ = await read_github_file(name)
        section = f"\n===== FILE: {name} =====\n{content}"

        if total_chars + len(section) > MAX_CONTEXT_CHARS:
            raise RuntimeError(
                f"Контекст проекта превышает лимит. Файл {name} "
                "не был обрезан или передан частично. Нужно анализировать "
                "проект отдельными частями."
            )

        sections.append(section)
        total_chars += len(section)

    if not sections:
        raise RuntimeError("Не найдены основные файлы проекта")

    return "\n".join(sections)


async def save_file(path: str, content: str, expected_sha=None):
    """
    Save only if the file still has the SHA recorded during preparation.
    This prevents overwriting a newer GitHub version.
    """
    path = safe_path(path)

    payload = {
        "message": f"Update {path}",
        "content": base64.b64encode(
            content.encode("utf-8")
        ).decode("ascii"),
        "branch": GITHUB_BRANCH,
    }

    try:
        _, current_sha = await read_github_file(path)

        if expected_sha is None:
            raise RuntimeError(
                f"Файл {path} уже существует. Подготовь изменения заново."
            )

        if current_sha != expected_sha:
            raise RuntimeError(
                f"Файл {path} изменился после подготовки. "
                "Изменения не сохранены — подготовь их заново."
            )

        payload["sha"] = current_sha

    except RuntimeError as error:
        if "404" not in str(error):
            raise

        if expected_sha is not None:
            raise RuntimeError(
                f"Файл {path} удалён после подготовки. "
                "Изменения не сохранены."
            )

    return await github_request("PUT", f"contents/{path}", payload)


# ============================================================
# OPENROUTER
# ============================================================

async def ask_ai(system_prompt: str, user_prompt: str, max_tokens=14000):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
    }

    timeout = ClientTimeout(total=180)

    async with ClientSession(timeout=timeout) as session:
        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
        ) as response:
            result = await response.json(content_type=None)

            if response.status != 200:
                raise RuntimeError(
                    f"OpenRouter ({response.status}): {str(result)[:1000]}"
                )

            choices = result.get("choices", [])

            if not choices:
                raise RuntimeError("ИИ не вернул ответ")

            choice = choices[0]
            content = choice.get("message", {}).get("content")

            if not isinstance(content, str) or not content.strip():
                raise RuntimeError("ИИ вернул пустой ответ")

            if choice.get("finish_reason") == "length":
                raise RuntimeError(
                    "Ответ ИИ обрезан из-за лимита токенов. "
                    "Изменения не подготовлены."
                )

            return content.strip()


# ============================================================
# NORMAL CHAT
# ============================================================

CHAT_SYSTEM = """
Ты — Губка GPT, личный ИИ-помощник пользователя.

Общайся на русском языке, естественно и по делу.
Помогай с вопросами, идеями, обучением и программированием.

Если тебе передан контекст GitHub-проекта, используй именно его.
Не утверждай, что читал файлы, запускал тесты, менял GitHub или выполнял
действия, если соответствующая операция реально не была выполнена.

Изменения проекта сначала только подготавливаются.
Записывать их в GitHub разрешено только после отдельного подтверждения /apply.
Если контекста проекта нет, не выдумывай содержимое репозитория.
"""


async def chat_with_ai(user_id: int, text: str, project_context=None):
    history = chat_history.setdefault(user_id, [])

    system_prompt = CHAT_SYSTEM
    if project_context:
        system_prompt += (
            "\n\nАКТУАЛЬНЫЙ КОНТЕКСТ GITHUB-ПРОЕКТА:\n"
            + project_context
        )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-10:])
    messages.append({"role": "user", "content": text})

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 2500,
    }

    timeout = ClientTimeout(total=120)

    async with ClientSession(timeout=timeout) as session:
        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
        ) as response:
            result = await response.json(content_type=None)

            if response.status != 200:
                raise RuntimeError(
                    f"OpenRouter ({response.status}): {str(result)[:800]}"
                )

            choices = result.get("choices", [])
            if not choices:
                raise RuntimeError("ИИ не вернул ответ")

            answer = choices[0].get("message", {}).get("content")

            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError("Получен пустой ответ")

    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": answer})
    chat_history[user_id] = history[-20:]

    return answer.strip()


# ============================================================
# CODE DEVELOPER
# ============================================================

CODE_SYSTEM = r"""
Ты — Губка GPT, ИИ-разработчик существующего Python-проекта.

Тебе переданы задача пользователя и текущие файлы проекта.

ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА:
1. Выполняй только задачу пользователя.
2. Внимательно изучай текущий код.
3. Сохраняй все существующие возможности и команды.
4. Возвращай полный новый текст каждого изменяемого файла.
5. Никогда не используй сокращения и заглушки вместо кода.
6. Не придумывай результаты тестов.
7. Не раскрывай секреты и токены.
8. Не добавляй секреты в файлы.
9. Не изменяй .env, .git и секретные файлы.
10. Не удаляй файлы.
11. Максимум пять изменяемых файлов.
12. Если задача уже выполнена, не возвращай файлы.
13. Если информации недостаточно, объясни это и не меняй файлы.
14. Не добавляй приветствия и посторонние функции.
15. Не используй JSON.

ФОРМАТ ОТВЕТА СТРОГО ТАКОЙ:

<<<GUBKA_SUMMARY>>>
Краткое описание изменений

<<<GUBKA_FILE: main.py>>>
Полное содержимое файла без Markdown-ограждений.
<<<GUBKA_END_FILE>>>

Для каждого дополнительного файла используй отдельный блок GUBKA_FILE.
Не используй специальные маркеры внутри кода.
Не добавляй текст до первого маркера или после последнего.
Не обрезай файлы.
"""


SUMMARY_MARKER = "<<<GUBKA_SUMMARY>>>"
FILE_PATTERN = re.compile(
    r"(?m)^<<<GUBKA_FILE:\s*(.*?)>>>[ \t]*\r?$"
)
END_MARKER = "<<<GUBKA_END_FILE>>>"


def extract_model_files(answer: str):
    answer = answer.strip()

    summary_position = answer.find(SUMMARY_MARKER)
    if summary_position == -1:
        raise ValueError("ИИ не вернул описание изменений")

    if answer[:summary_position].strip():
        raise ValueError("ИИ добавил лишний текст перед описанием изменений")

    summary_start = summary_position + len(SUMMARY_MARKER)
    matches = list(FILE_PATTERN.finditer(answer, summary_start))

    if not matches:
        summary = answer[summary_start:].strip()
        if not summary:
            raise ValueError("ИИ вернул пустой ответ")
        return summary, []

    summary = answer[summary_start:matches[0].start()].strip()
    if not summary:
        raise ValueError("ИИ не объяснил подготовленные изменения")

    files_by_path = {}

    for index, match in enumerate(matches):
        raw_path = match.group(1).strip()

        if not raw_path or "{" in raw_path or "}" in raw_path:
            raise ValueError("ИИ указал некорректное имя файла")

        path = safe_path(raw_path)
        body_start = match.end()

        if body_start < len(answer) and answer[body_start] == "\n":
            body_start += 1

        end_position = answer.find(END_MARKER, body_start)
        next_file_position = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else -1
        )

        if end_position == -1 or (
            next_file_position != -1 and next_file_position < end_position
        ):
            raise ValueError(
                f"Блок файла {path} обрезан или не закрыт. "
                "Такой файл нельзя безопасно использовать."
            )

        content = answer[body_start:end_position]
        content = content.rstrip("\r\n") + "\n"

        if not content.strip():
            raise ValueError(f"Файл {path} получился пустым")

        after_end = end_position + len(END_MARKER)

        if next_file_position != -1:
            between = answer[after_end:next_file_position]
            if between.strip():
                raise ValueError("ИИ добавил лишний текст между файлами")
        else:
            trailing = answer[after_end:]
            if trailing.strip():
                raise ValueError("ИИ добавил лишний текст после последнего файла")

        previous = files_by_path.get(path)

        if previous is not None:
            if previous != content:
                raise ValueError(
                    f"ИИ вернул разные версии одного файла: {path}. "
                    "Подготовка отменена, чтобы не потерять код."
                )
            # Идентичный повторный блок пропускается.
            continue

        files_by_path[path] = content

    files = [
        {"path": path, "content": content}
        for path, content in files_by_path.items()
    ]

    return summary, files


async def prepare_changes(task: str):
    project = await get_project_context()

    user_prompt = (
        "ЗАДАЧА ПОЛЬЗОВАТЕЛЯ:\n"
        f"{task}\n\n"
        "ТЕКУЩИЙ КОД ПРОЕКТА:\n"
        f"{project}\n\n"
        "Выполни только указанную задачу. Верни полное содержимое "
        "изменяемых файлов в формате специальных разделителей."
    )

    answer = await ask_ai(CODE_SYSTEM, user_prompt)
    summary, files = extract_model_files(answer)

    if len(files) > MAX_FILES_PER_CHANGE:
        raise ValueError("ИИ вернул слишком много разных файлов")

    checked = []

    for item in files:
        path = safe_path(item["path"])
        content = item["content"]

        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError(f"Файл слишком большой: {path}")

        try:
            _, expected_sha = await read_github_file(path)
        except RuntimeError as error:
            if "404" in str(error):
                expected_sha = None
            else:
                raise

        checked.append({
            "path": path,
            "content": content,
            "expected_sha": expected_sha,
        })

    return summary, checked


# ============================================================
# PROJECT INTENT ROUTING
# ============================================================

def detect_project_intent(text: str):
    value = text.lower()

    project_terms = (
        "губк", "бот", "проект", "репозитор", "github",
        "main.py", "requirements.txt", "код бота", "файл бота",
    )
    inspect_terms = (
        "проверь", "посмотри", "изучи", "прочитай", "найди ошиб",
        "почему не работает", "проанализируй", "покажи файлы",
    )
    edit_terms = (
        "добавь", "измени", "исправь", "создай", "перепиши",
        "улучши", "реализуй", "добавить", "исправить",
    )

    if not any(term in value for term in project_terms):
        return None

    if any(term in value for term in edit_terms):
        return "edit"

    if any(term in value for term in inspect_terms):
        return "inspect"

    return "context"


async def inspect_project(message: Message, question: str):
    await message.answer("Читаю актуальные файлы GitHub и анализирую проект...")

    try:
        context = await get_project_context()
        prompt = (
            "Проанализируй проект только по переданным файлам. "
            "Указывай конкретные функции и файлы. Не утверждай, что "
            "запускал тесты или сервер. Если информации недостаточно, "
            "скажи об этом.\n\n"
            f"ВОПРОС:\n{question}\n\n"
            f"ФАЙЛЫ ПРОЕКТА:\n{context}"
        )

        answer = await ask_ai(
            "Ты — технический аналитик Python-проектов. "
            "Отвечай на русском, точно и понятно.",
            prompt,
            max_tokens=3500,
        )

        await send_long(message, answer)

    except Exception as error:
        await message.answer(
            f"Не удалось проанализировать проект:\n{str(error)[:1200]}"
        )


async def prepare_and_stage(message: Message, task: str):
    user_id = message.from_user.id
    await message.answer("Изучаю GitHub и готовлю изменения...")

    try:
        summary, files = await prepare_changes(task)

        if not files:
            await message.answer(f"Изменения не нужны.\n\n{summary}")
            return

        pending_changes[user_id] = {
            "task": task,
            "summary": summary,
            "files": files,
        }

        lines = [
            "ПОДГОТОВЛЕНЫ ИЗМЕНЕНИЯ",
            "",
            f"Задача: {task}",
            "",
            f"Описание: {summary}",
            "",
            "Файлы:",
        ]

        for item in files:
            count = item["content"].count("\n")
            state = (
                "новый файл"
                if item["expected_sha"] is None
                else "замена существующего"
            )
            lines.append(f"📄 {item['path']} — {count} строк, {state}")

        lines.extend([
            "",
            "В GitHub пока ничего не записано.",
            "/pending — посмотреть подготовку",
            "/apply — сохранить",
            "/cancel — отменить",
        ])

        await send_long(message, "\n".join(lines))

    except Exception as error:
        await message.answer(
            f"Не удалось подготовить изменения:\n{str(error)[:1500]}"
        )


# ============================================================
# TELEGRAM COMMANDS
# ============================================================

@dp.message(Command("start"))
async def start(message: Message):
    if not allowed(message):
        return

    await message.answer(
        "Привет! Я Губка GPT.\n\n"
        "Я могу общаться, анализировать проект и готовить изменения GitHub.\n\n"
        "Обычные сообщения — для общения.\n"
        "/code — изменить проект\n"
        "/inspect — анализ проекта\n"
        "/pending — ожидающие изменения\n"
        "/help — все команды"
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
        "/write файл.py текст — подготовить запись файла\n"
        "/code задача — поручить ИИ изменить проект\n"
        "/inspect — анализ проекта\n"
        "/pending — список ожидающих изменений\n"
        "/apply — подтвердить и сохранить изменения\n"
        "/cancel — отменить изменения\n"
        "/reset — очистить историю чата\n\n"
        "Изменения GitHub сохраняются только после /apply."
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
            f"Репозиторий: {repo.get('full_name', GITHUB_REPO)}\n"
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
            f"Репозиторий: {data.get('full_name')}\n"
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
            lines.append(f"{icon} {item.get('name', 'Без имени')}")

        await message.answer("\n".join(lines) or "Папка пустая")

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
        await send_long(message, f"Файл: {args[1]}\n\n{content}")
    except Exception as error:
        await message.answer(f"Ошибка: {error}")


@dp.message(Command("write"))
async def write(message: Message):
    if not allowed(message):
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "Формат: /write файл.py текст\n"
            "Файл будет подготовлен, но записан только после /apply."
        )
        return

    try:
        path = safe_path(parts[1])
        content = parts[2]

        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError("Файл слишком большой (лимит 50 КБ)")

        try:
            _, expected_sha = await read_github_file(path)
        except RuntimeError as error:
            if "404" in str(error):
                expected_sha = None
            else:
                raise

        pending_changes[message.from_user.id] = {
            "task": f"Создать или обновить {path}",
            "summary": "Файл подготовлен командой /write.",
            "files": [{
                "path": path,
                "content": content,
                "expected_sha": expected_sha,
            }],
        }

        await message.answer(
            f"Файл {path} подготовлен. В GitHub ничего не записано.\n"
            "Используй /pending, затем /apply или /cancel."
        )

    except Exception as error:
        await message.answer(f"Ошибка: {error}")


@dp.message(Command("code"))
async def code_command(message: Message):
    if not allowed(message):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Формат: /code задача")
        return

    async with get_lock(message.from_user.id):
        await prepare_and_stage(message, parts[1].strip())


@dp.message(Command("inspect"))
async def inspect_command(message: Message):
    if not allowed(message):
        return

    args = (message.text or "").split(maxsplit=1)
    question = (
        args[1].strip()
        if len(args) > 1
        else "Проведи обзор архитектуры, функций, рисков и приоритетных улучшений."
    )

    async with get_lock(message.from_user.id):
        await inspect_project(message, question)


@dp.message(Command("pending"))
async def pending_command(message: Message):
    if not allowed(message):
        return

    changes = pending_changes.get(message.from_user.id)
    if not changes:
        await message.answer("Нет подготовленных изменений.")
        return

    lines = [
        "ИЗМЕНЕНИЯ ОЖИДАЮТ ПОДТВЕРЖДЕНИЯ",
        "",
        changes["summary"],
        "",
        "Файлы:",
    ]

    for item in changes["files"]:
        count = item["content"].count("\n")
        lines.append(f"• {item['path']} — {count} строк")

    lines.extend(["", "/apply — сохранить", "/cancel — отменить"])
    await send_long(message, "\n".join(lines))


@dp.message(Command("apply"))
async def apply(message: Message):
    if not allowed(message):
        return

    user_id = message.from_user.id

    async with get_lock(user_id):
        changes = pending_changes.get(user_id)

        if not changes:
            await message.answer("Нет изменений для подтверждения.")
            return

        await message.answer("Проверяю файлы и отправляю изменения в GitHub...")

        try:
            # Preflight all files before writing any of them.
            for item in changes["files"]:
                path = item["path"]

                try:
                    _, current_sha = await read_github_file(path)
                except RuntimeError as error:
                    if "404" in str(error):
                        current_sha = None
                    else:
                        raise

                if current_sha != item["expected_sha"]:
                    raise RuntimeError(
                        f"Файл {path} изменился после подготовки. "
                        "Ничего не записано. Подготовь изменения заново."
                    )

            saved = []

            for item in changes["files"]:
                await save_file(
                    item["path"],
                    item["content"],
                    expected_sha=item["expected_sha"],
                )
                saved.append(item["path"])

            pending_changes.pop(user_id, None)

            await message.answer(
                "Изменения сохранены в GitHub!\n\n"
                + "\n".join(f"📄 {path}" for path in saved)
                + "\n\nRender должен начать новый деплой."
            )

        except Exception as error:
            await message.answer(
                "Ошибка при сохранении:\n"
                f"{str(error)[:1200]}\n\n"
                "Если сохранялось несколько файлов, проверь GitHub: "
                "GitHub API не объединяет несколько файлов в одну атомарную операцию."
            )


@dp.message(Command("cancel"))
async def cancel(message: Message):
    if not allowed(message):
        return

    pending_changes.pop(message.from_user.id, None)
    await message.answer(
        "Подготовленные изменения отменены. В GitHub ничего не отправлено."
    )


@dp.message(Command("reset"))
async def reset(message: Message):
    if not allowed(message):
        return

    chat_history.pop(message.from_user.id, None)
    await message.answer("История обычного чата очищена.")


# ============================================================
# SMART NORMAL CHAT ROUTER
# ============================================================

@dp.message()
async def ordinary_chat(message: Message):
    if not allowed(message):
        return

    text = (message.text or "").strip()
    if not text:
        return

    if text.startswith("/"):
        await message.answer("Неизвестная команда. Напиши /help.")
        return

    user_id = message.from_user.id
    intent = detect_project_intent(text)

    async with get_lock(user_id):
        if intent == "edit":
            await prepare_and_stage(message, text)
            return

        if intent == "inspect":
            await inspect_project(message, text)
            return

        await message.answer("Думаю...")

        try:
            project_context = None

            if intent == "context":
                project_context = await get_project_context()

            answer = await chat_with_ai(
                user_id,
                text,
                project_context=project_context,
            )
            await send_long(message, answer)

        except Exception as error:
            await message.answer(
                f"Не получилось получить ответ:\n{str(error)[:1200]}"
            )


# ============================================================
# WEB HEALTH CHECK / STARTUP
# ============================================================

async def main():
    app = web.Application()

    async def health(_request):
        return web.Response(text="Губка GPT работает!")

    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print("Губка GPT запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
