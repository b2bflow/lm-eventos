import redis
import os
from interfaces.clients.cache_interface import ICache


class RedisClient(ICache):

    def __init__(self):
        self._redis = redis.Redis(
            host=os.getenv("REDIS_HOST"),
            port=int(os.getenv("REDIS_PORT")),
            password=os.getenv("REDIS_PASSWORD"),
            decode_responses=True,
        )

    # Comunicação básica

    def set(self, key: str, value: str, expiration_seconds: int = None) -> bool:
        try:
            if expiration_seconds:
                return self._redis.setex(key, expiration_seconds, value)

            return self._redis.set(key, value)
        except Exception:
            return False

    def get(self, key: str) -> str:
        return self._redis.get(key)

    def delete(self, key: str) -> bool:
        return bool(self._redis.delete(key))

    def exists(self, key: str) -> bool:
        return bool(self._redis.exists(key))

    # Hash genéricos
    def hgetall(self, name: str) -> dict:
        return self._redis.hgetall(name)

    def hget(self, name: str, key: str) -> str:
        return self._redis.hget(name, key)

    def hset(self, name: str, key: str, value: str) -> int:
        return self._redis.hset(name, key, value)

    def hdel(self, name: str, *keys: str) -> int:
        return self._redis.hdel(name, *keys)
