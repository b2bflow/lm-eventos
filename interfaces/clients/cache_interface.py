from abc import ABC, abstractmethod


class ICache(ABC):

    @abstractmethod
    def set(self, key: str, value: str, expiration_seconds: int = None) -> bool:
        pass

    @abstractmethod
    def get(self, key: str) -> str:
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        pass

    # Métodos genéricos de Hash para comunicação com Redis
    @abstractmethod
    def hgetall(self, name: str) -> dict:
        pass

    @abstractmethod
    def hget(self, name: str, key: str) -> str:
        pass

    @abstractmethod
    def hset(self, name: str, key: str, value: str) -> int:
        pass

    @abstractmethod
    def hdel(self, name: str, *keys: str) -> int:
        pass
