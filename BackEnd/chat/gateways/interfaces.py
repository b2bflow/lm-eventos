from abc import ABC, abstractmethod
from typing import Dict, Any

class IEventGateway(ABC):
    @abstractmethod
    def emit_new_message(self, event_data: Dict[str, Any]) -> None:
        pass