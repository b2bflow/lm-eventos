import os
from urllib.parse import parse_qs

import socketio
from asgiref.sync import sync_to_async

redis_url = os.environ.get("REDIS_URL")


def allowed_origins() -> list[str]:
    """Mesmas origens do CORS da API (CORS_ALLOWED_ORIGINS). Nunca '*': o socket transmite as
    mensagens do WhatsApp de todos os clientes."""
    return [o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]


def token_from(environ: dict, auth) -> str:
    """JWT de acesso enviado pelo front em `auth: {token}` (ou ?token= no handshake)."""
    if isinstance(auth, dict) and auth.get("token"):
        return str(auth["token"])
    query = parse_qs(environ.get("QUERY_STRING", ""))
    return (query.get("token") or [""])[0]


def user_id_from_token(token: str):
    """Id do usuário ativo dono do token de acesso, ou None se o token for inválido ou expirado."""
    if not token:
        return None
    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import AccessToken
    from users.models.user_model import User

    try:
        user_id = AccessToken(token).get("user_id")
    except TokenError:
        return None
    return user_id if User.objects.filter(id=user_id, is_active=True).exists() else None


# O servidor ASGI necessita da versão Async
mgr = socketio.AsyncRedisManager(redis_url)

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=allowed_origins(),
    client_manager=mgr
)


@sio.event
async def connect(sid, environ, auth=None):
    """Só usuário logado recebe eventos (new_message leva conteúdo e telefone dos clientes)."""
    user_id = await sync_to_async(user_id_from_token)(token_from(environ, auth))
    if not user_id:
        raise socketio.exceptions.ConnectionRefusedError("unauthorized")
    await sio.save_session(sid, {"user_id": user_id})
