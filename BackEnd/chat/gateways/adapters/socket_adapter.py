import os
import socketio
from utils.logger import logger
from chat.gateways.interfaces import IEventGateway 


class SocketAdapter(IEventGateway): 
    def __init__(self):
        self.redis_url = os.environ.get("REDIS_URL")

    def emit_new_message(self, payload: dict) -> None: 
        try:
            external_mgr = socketio.RedisManager(self.redis_url, write_only=True)
            external_mgr.emit('new_message', data=payload)
            logger.info("[SocketAdapter] Socket emitido com sucesso via barramento Redis.")
        except Exception as e:
            logger.error(f"[SocketAdapter] Falha de emissão no SocketAdapter: {e}")
            raise e