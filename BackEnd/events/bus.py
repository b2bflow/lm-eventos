from typing import Callable, Dict, List
from utils.logger import logger
from events.interfaces.bus_interface import IEventBus

class EventBus(IEventBus):
    _subscribers: Dict[str, List[Callable]] = {}

    @classmethod
    def subscribe(self, event_name: str, handler: Callable) -> None:
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        self._subscribers[event_name].append(handler)
        logger.info(f"[EventBus] Handler {handler.__name__} inscrito no evento: {event_name}")

    @classmethod
    def publish(self, event_name: str, payload: dict) -> None:
        try:
            from events.tasks import dispatch_event_task
            logger.info(f"[EventBus] Publicando evento assíncrono: {event_name}")
            dispatch_event_task.delay(event_name, payload)
        except Exception as e:
            logger.error(f"[EventBus] Erro ao publicar evento {event_name}: {str(e)}")
            raise e

    @classmethod
    def handle_event(self, event_name: str, payload: dict) -> None:
        handlers = self._subscribers.get(event_name, [])
        for handler in handlers:
            try:
                handler(payload)
            except Exception as e:
                logger.error(f"[EventBus] Erro no handler {handler.__name__} para evento {event_name}: {str(e)}")

    @classmethod
    def publish_sync(self, event_name: str, payload: dict) -> None:
        try:
            logger.info(f"[EventBus] Publicando evento síncrono: {event_name}")
            self.handle_event(event_name, payload)
        except Exception as e:
            logger.error(f"[EventBus] Erro no evento síncrono {event_name}: {str(e)}")
            raise e