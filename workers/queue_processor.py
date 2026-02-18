from __future__ import annotations

import os
import json
import time
import asyncio
from typing import TYPE_CHECKING

from interfaces.clients.cache_interface import ICache
from utils.logger import logger, to_json_dump

if TYPE_CHECKING:
    from services.generate_response_service import GenerateResponseService


class Queue:
    WAITING_STATUS = "waiting"
    QUEUED_STATUS = "queued"
    PROCESSING_STATUS = "processing"

    def __init__(
        self,
        cache_client: ICache,
        generate_response_service: GenerateResponseService | None = None,
        queue_key: str | None = None,
        queue_debounce_seconds: int | None = None,
        use_threads: bool | None = None,
    ) -> None:
        self._cache = cache_client
        self._generate_response = generate_response_service
        self._queue_key = queue_key or os.getenv("QUEUE_KEY", "message_queue")
        self._queue_debounce_seconds = int(
            queue_debounce_seconds or os.getenv("QUEUE_DEBOUNCE_SECONDS", "5")
        )
        self._max_retries = int(os.getenv("QUEUE_MAX_RETRIES", "3"))
        self.queue_retry_delay_seconds = int(
            os.getenv("QUEUE_RETRY_DELAY_SECONDS", "15")
        )

        # Quando True, processa cada item em uma Thread separada, evitando bloquear o event loop
        # Pode ser controlado por env QUEUE_USE_THREADS (default True)
        env_use_threads = os.getenv("QUEUE_USE_THREADS")
        self._use_threads = use_threads or (
            False if env_use_threads == "false" else True
        )
        # Limite de concorrência (quantos itens podem ser processados simultaneamente)
        self._max_concurrency = int(os.getenv("QUEUE_MAX_CONCURRENCY", 10))
        self._semaphore = asyncio.Semaphore(self._max_concurrency)

    def set_generate_response_service(self, service: GenerateResponseService) -> None:
        self._generate_response = service

    async def run(self) -> None:
        logger.info(
            f'[QUEUE] Iniciando processamento da fila "{self._queue_key}" com debounce {self._queue_debounce_seconds}s.'
        )

        while True:
            try:
                await self._tick()
            except Exception as e:
                logger.exception(
                    f"[QUEUE] ❌ Erro no loop da fila: \n{to_json_dump(e)}"
                )
            await asyncio.sleep(1)

    async def _tick(self) -> None:
        now = time.time()
        # Lê o hash da fila via métodos genéricos
        queue = self._cache.hgetall(self._queue_key) or {}

        for phone, raw_data in queue.items():
            data = self._safe_parse(raw_data, phone)
            if not data:
                self._cache.hdel(self._queue_key, phone)
                continue

            status = data.get("status")
            expired_at = float(data.get("expired_at", now + 1))

            # Evita duplicidade durante processamento ou fila aguardando vaga
            if status in (self.PROCESSING_STATUS, self.QUEUED_STATUS):
                continue

            if expired_at > now:
                continue

            # Marca como queued e dispara a geração em paralelo
            data["status"] = self.QUEUED_STATUS
            data["queued_at"] = now
            self._set_queue_item(phone, data)

            if self._use_threads:
                asyncio.create_task(self._bounded_thread_process(phone, data))
            else:
                asyncio.create_task(self._bounded_async_process(phone, data))

    async def _bounded_async_process(self, phone: str, data: dict[str, object]) -> None:
        async with self._semaphore:
            self._mark_processing(phone, data)
            await self._process_item(phone, data)

    async def _bounded_thread_process(
        self, phone: str, data: dict[str, object]
    ) -> None:
        async with self._semaphore:
            self._mark_processing(phone, data)
            await self._process_item_in_thread(phone, data)

    async def _process_item(self, phone: str, data: dict[str, object]) -> None:
        """Executa a geração e faz o cleanup (deleção) ao finalizar."""
        try:
            await self._generate_response.execute(
                phone=phone, message=str(data.get("value", ""))
            )

            # Sucesso: remove da fila somente se não houver nova mensagem "waiting"/"queued"
            raw = self._cache.hget(self._queue_key, phone)
            if raw:
                try:
                    current = json.loads(raw)
                except Exception:
                    current = {}
                status_now = current.get("status")
                if status_now in (self.WAITING_STATUS, self.QUEUED_STATUS):
                    logger.info(
                        f"[QUEUE] ➿ Nova entrada detectada para {phone} (status={status_now}). Mantendo item na fila."
                    )
                else:
                    self._cache.hdel(self._queue_key, phone)
            else:
                self._cache.hdel(self._queue_key, phone)
            logger.info(
                f"[QUEUE] ✅ Processamento concluído e removido da fila: {phone}"
            )
        except Exception as e:
            logger.exception(
                f"[QUEUE] ❌ Erro ao processar mensagem da fila para {phone}: \n{to_json_dump(e)}"
            )

            if data.get("retry_count", 0) < self._max_retries:
                now = time.time()
                retry = {
                    "value": data.get("value", ""),
                    "expired_at": now + self.queue_retry_delay_seconds,
                    "status": self.WAITING_STATUS,
                    "last_error": str(e),
                    "retry_count": data.get("retry_count", 0) + 1,
                }
                self._set_queue_item(phone, retry)
                logger.info(f"[QUEUE] 🔁 Item reagendado para nova tentativa: {phone}")

            else:
                logger.info(
                    f"[QUEUE] ⚠️ Máximo de tentativas atingido para {phone}. Removendo da fila."
                )

    async def _process_item_in_thread(
        self, phone: str, data: dict[str, object]
    ) -> None:
        """Executa todo o processamento em uma thread separada, incluindo cleanup."""

        def _blocking_run():
            try:
                # Executa a coroutine em um event loop próprio dentro da thread
                asyncio.run(
                    self._generate_response.execute(
                        phone=phone, message=str(data.get("value", ""))
                    )
                )

                # Sucesso: remove da fila somente se não houver nova mensagem "waiting"/"queued"
                raw = self._cache.hget(self._queue_key, phone)
                if raw:
                    try:
                        current = json.loads(raw)
                    except Exception:
                        current = {}
                    status_now = current.get("status")
                    if status_now in (self.WAITING_STATUS, self.QUEUED_STATUS):
                        logger.info(
                            f"[QUEUE] ➿ (thread) Nova entrada detectada para {phone} (status={status_now}). Mantendo item na fila."
                        )
                    else:
                        self._cache.hdel(self._queue_key, phone)
                else:
                    self._cache.hdel(self._queue_key, phone)
                logger.info(
                    f"[QUEUE] ✅ (thread) Processamento concluído e removido da fila: {phone}"
                )
            except Exception as e:
                logger.exception(
                    f"[QUEUE] ❌ (thread) Erro ao processar mensagem da fila para {phone}: \n{to_json_dump(e)}"
                )

                # Reagenda para tentar novamente no futuro
                if data.get("retry_count", 0) < self._max_retries:
                    now_local = time.time()
                    retry_local = {
                        "value": data.get("value", ""),
                        "expired_at": now_local + self.queue_retry_delay_seconds,
                        "status": self.WAITING_STATUS,
                        "last_error": str(e),
                        "retry_count": data.get("retry_count", 0) + 1,
                    }
                    self._set_queue_item(phone, retry_local)

                    logger.info(
                        f"[QUEUE] 🔁 (thread) Item reagendado para nova tentativa: {phone}"
                    )

                else:
                    logger.info(
                        f"[QUEUE] ⚠️ (thread) Máximo de tentativas atingido para {phone}. Removendo da fila."
                    )

        # Offload para thread
        await asyncio.to_thread(_blocking_run)

    def _safe_parse(self, raw_data: str, phone: str) -> dict[str, object] | None:
        try:
            return json.loads(raw_data)
        except Exception as e:
            logger.exception(
                f"[QUEUE] ❌ JSON inválido para chave {phone}: {raw_data}. Erro: {to_json_dump(e)}"
            )
            return None

    def _set_queue_item(self, phone: str, payload: dict[str, object]) -> None:
        """Atualiza/define o item da fila com JSON serializado."""
        # Preferir métodos expostos pelo cliente; fallback para delete+add_to_queue se necessário
        # Atualiza diretamente via hash genérico como JSON
        self._cache.hset(self._queue_key, phone, json.dumps(payload))

    def _mark_processing(self, phone: str, fallback_data: dict[str, object]) -> None:
        """Atualiza o status do item para 'processing' ao adquirir o semáforo."""
        raw = self._cache.hget(self._queue_key, phone)
        if raw:
            try:
                data = json.loads(raw)
            except Exception:
                data = dict(fallback_data)
        else:
            data = dict(fallback_data)

        data["status"] = self.PROCESSING_STATUS
        data["processing_started_at"] = time.time()
        self._cache.hset(self._queue_key, phone, json.dumps(data))

    def exists(self, phone: str, status: str) -> bool:
        raw = self._cache.hget(self._queue_key, phone)
        if not raw:
            return False

        try:
            data = json.loads(raw)
        except Exception:
            return False

        return data.get("status") == status

    def delete(self, phone: str) -> int:
        """Remove um item da fila pela chave (phone). Retorna a quantidade removida (0 ou 1)."""
        return self._cache.hdel(self._queue_key, phone)

    @staticmethod
    def enqueue(
        cache_client: ICache,
        queue_key: str,
        key: str,
        value: str,
        append: bool = False,
        queue_debounce_seconds: int | None = None,
    ) -> int:
        """Adiciona/atualiza um item na fila como JSON com expired_at e valor, usando hash genérico.

        Retorna quantos segundos até expirar (debounce aplicado).
        """
        debounce = int(
            queue_debounce_seconds or int(os.getenv("QUEUE_DEBOUNCE_SECONDS", 5))
        )
        now = time.time()
        expired_at = now + debounce

        queue = cache_client.hgetall(queue_key) or {}
        if key in queue:
            try:
                data = json.loads(queue[key])
            except Exception:
                data = {}

            prev_value = data.get("value", "")

            data["expired_at"] = expired_at
            data["value"] = f"{prev_value} \n{value}".strip() if append else value
            data["status"] = Queue.WAITING_STATUS
            data["retry_count"] = 0

            cache_client.hset(queue_key, key, json.dumps(data))

            return int(data["expired_at"] - now)

        payload = {
            "value": value,
            "expired_at": expired_at,
            "status": Queue.WAITING_STATUS,
        }
        cache_client.hset(queue_key, key, json.dumps(payload))
        return debounce
