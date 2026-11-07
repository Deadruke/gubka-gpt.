import os
import secrets
import time
import contextvars

from urllib.parse import urlencode

from aiohttp import web


CLIENT_ID = os.getenv("GITHUB_OAUTH_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("GITHUB_OAUTH_CLIENT_SECRET", "").strip()

BASE_URL = os.getenv(
    "WEB_APP_URL",
    "https://gubka-gpt.onrender.com"
).strip().rstrip("/")

CALLBACK_URL = BASE_URL + "/auth/github/callback"

SESSION_TTL = 60 * 60 * 24 * 14
STATE_TTL = 600

sessions = {}
oauth_states = {}

github_token_context = contextvars.ContextVar(
    "github_token_context",
    default=None
)


def github_token_for_request():
    return github_token_context.get()


@web.middleware
async def oauth_middleware(request, handler):
    token = None
    session_id = request.cookies.get("gubka_session", "")
    record = sessions.get(session_id)

    if record:
        if time.time() - record["created"] > SESSION_TTL:
            sessions.pop(session_id, None)
        else:
            token = record["access_token"]

    context_token = github_token_context.set(token)

    try:
        return await handler(request)
    finally:
        github_token_context.reset(context_token)


def get_authenticated_user(request):
    session_id = request.cookies.get("gubka_session", "")
    record = sessions.get(session_id)

    if not record:
        raise web.HTTPUnauthorized(
            text="Войди через Telegram или GitHub."
        )

    if time.time() - record["created"] > SESSION_TTL:
        sessions.pop(session_id, None)

        raise web.HTTPUnauthorized(
            text="Сессия истекла. Войди снова."
        )

    return {
        "id": record["id"],
        "login": record["login"],
        "first_name": record["name"],
        "provider": "github"
    }


async def github_login(request):
    if not CLIENT_ID or not CLIENT_SECRET:
        raise web.HTTPServiceUnavailable(
            text="GitHub OAuth не настроен в Render."
        )

    state = secrets.token_urlsafe(32)
    oauth_states[state] = time.time()

    for key, created in list(oauth_states.items()):
        if time.time() - created > STATE_TTL:
            oauth_states.pop(key, None)

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": CALLBACK_URL,
        "scope": "repo",
        "state": state
    }

    response = web.HTTPFound(
        "https://github.com/login/oauth/authorize?"
        + urlencode(params)
    )

    response.set_cookie(
        "gubka_oauth_state",
        state,
        max_age=STATE_TTL,
        httponly=True,
        secure=True,
        samesite="Lax",
        path="/"
    )

    raise response


async def github_callback(request):
    if not CLIENT_ID or not CLIENT_SECRET:
        raise web.HTTPServiceUnavailable(
            text="GitHub OAuth не настроен."
        )

    code = request.query.get("code", "")
    state = request.query.get("state", "")

    saved_state = request.cookies.get(
        "gubka_oauth_state",
        ""
    )

    created = oauth_states.pop(state, None)

    if (
        not code
        or not state
        or not saved_state
        or not secrets.compare_digest(state, saved_state)
        or created is None
        or time.time() - created > STATE_TTL
    ):
        raise web.HTTPBadRequest(
            text="Авторизация устарела. Попробуй войти снова."
        )

    session = request.app["oauth_http_session"]

    async with session.post(
        "https://github.com/login/oauth/access_token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": CALLBACK_URL
        },
        headers={
            "Accept": "application/json",
            "User-Agent": "Gubka-GPT"
        }
    ) as response:
        token_data = await response.json(content_type=None)

        if (
            response.status >= 400
            or not token_data.get("access_token")
        ):
            raise web.HTTPBadGateway(
                text="GitHub не выдал токен авторизации."
            )

    access_token = token_data["access_token"]

    async with session.get(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "Gubka-GPT",
            "X-GitHub-Api-Version": "2022-11-28"
        }
    ) as response:
        user = await response.json(content_type=None)

        if response.status >= 400:
            raise web.HTTPBadGateway(
                text="Не удалось получить профиль GitHub."
            )

    if not user.get("id") or not user.get("login"):
        raise web.HTTPBadGateway(
            text="GitHub вернул неполный профиль."
        )

    session_id = secrets.token_urlsafe(48)

    sessions[session_id] = {
        "id": int(user["id"]),
        "login": user["login"],
        "name": user.get("name") or user["login"],
        "access_token": access_token,
        "created": time.time()
    }

    result = web.HTTPFound("/")

    result.set_cookie(
        "gubka_session",
        session_id,
        max_age=SESSION_TTL,
        httponly=True,
        secure=True,
        samesite="Lax",
        path="/"
    )

    result.del_cookie(
        "gubka_oauth_state",
        path="/"
    )

    raise result


async def github_logout(request):
    session_id = request.cookies.get("gubka_session", "")
    sessions.pop(session_id, None)

    response = web.json_response({
        "ok": True
    })

    response.del_cookie(
        "gubka_session",
        path="/"
    )

    return response


def register_oauth_routes(app, http_session):
    app["oauth_http_session"] = http_session

    app.middlewares.append(oauth_middleware)

    app.router.add_get(
        "/auth/github",
        github_login
    )

    app.router.add_get(
        "/auth/github/callback",
        github_callback
    )

    app.router.add_post(
        "/auth/logout",
        github_logout
    )
