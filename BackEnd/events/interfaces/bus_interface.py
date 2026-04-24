from abc import ABC, abstractmethod
from typing import Callable

class IEventBus(ABC):
    @abstractmethod
    def publish(self, event_name: str, payload: dict) -> None:
        pass

    @abstractmethod
    def publish_sync(self, event_name: str, payload: dict) -> None:
        pass

    @abstractmethod
    def subscribe(self, event_name: str, handler: Callable) -> None:
        pass

    @abstractmethod
    def handle_event(self, event_name: str, payload: dict) -> None:
        pass