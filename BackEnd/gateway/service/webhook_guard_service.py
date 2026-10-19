import hashlib
import hmac
import os

import redis

from utils.logger import logger


class WebhookGuardService:
    """Proteções do webhook da Z-API: token obrigatório e descarte de mensagens repetidas.

    Token: comparado com ZAPI_WEBHOOK_TOKEN (ou, se vazio, com SystemConfig.webhook_token).
    Aceito no cabeçalho X-Webhook-Token ou na querystring ?token= (a Z-API só permite configurar URL).
    Sem token configurado, todo webhook é recusado.

    Repetição: mesmo número + mesmo texto em até WEBHOOK_DEDUP_SECONDS (padrão 120 s) é ignorado
    (clique repetido em anúncio). Reentrega da Z-API com o mesmo messageId também é ignorada.
    Se o Redis estiver fora, a mensagem passa (nunca perder mensagem por falha de infraestrutura).
    """

    HEADER = "HTTP_X_WEBHOOK_TOKEN"
    MESSAGE_ID_TTL = 60 * 60 * 24

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self.dedup_seconds = int(os.getenv("WEBHOOK_DEDUP_SECONDS", "120"))

    @property
    def redis(self):
        if self._redis is None:
            self._redis = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        return self._redis

    def expected_token(self) -> str:
        token = os.getenv("ZAPI_WEBHOOK_TOKEN", "").strip()
        if token:
            return token
        try:
            from chat.repositories.system_config_repository import SystemConfigRepository
            return (SystemConfigRepository.get_config().webhook_token or "").strip()
        except Exception as e:
            logger.error(f"[WebhookGuard] Falha ao ler token do SystemConfig: {e}")
            return ""

    def is_authorized(self, request) -> bool:
        expected = self.expected_token()
        if not expected:
            logger.error("[WebhookGuard] Nenhum token de webhook configurado (ZAPI_WEBHOOK_TOKEN). Requisição recusada.")
            return False
        received = request.META.get(self.HEADER) or request.query_params.get("token") or ""
        # Em bytes: compare_digest com str não ASCII levanta TypeError (500 em vez de 401).
        return hmac.compare_digest(str(received).encode("utf-8"), expected.encode("utf-8"))

    def is_duplicate(self, data: dict) -> bool:
        phone = str(data.get("phone") or "")
        if not phone:
            return False
        try:
            message_id = data.get("messageId")
            if message_id and not self.redis.set(f"wh:msgid:{message_id}", 1, nx=True, ex=self.MESSAGE_ID_TTL):
                return True

            text = (data.get("text") or {}).get("message") if isinstance(data.get("text"), dict) else None
            if not text:
                return False
            digest = hashlib.sha1(text.strip().lower().encode("utf-8")).hexdigest()
            return not self.redis.set(f"wh:dedup:{phone}:{digest}", 1, nx=True, ex=self.dedup_seconds)
        except redis.RedisError as e:
            logger.warning(f"[WebhookGuard] Redis indisponível, deduplicação ignorada: {e}")
            return False
