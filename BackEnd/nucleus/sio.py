import os
import socketio

redis_url = os.environ.get("REDIS_URL")

# O servidor ASGI necessita da versão Async
mgr = socketio.AsyncRedisManager(redis_url)

sio = socketio.AsyncServer(
    async_mode='asgi', 
    cors_allowed_origins='*',
    client_manager=mgr
)
