from services.message_queue_service import MessageQueueService
from interfaces.clients.database_interface import IDatabase


class ProcessIncomingMessageController:

    def __init__(self, message_queue_service: MessageQueueService):
        self.message_queue_service = message_queue_service

    def handle(self, **kwargs) -> tuple[dict, int]:
        self.message_queue_service.handle(**kwargs)

        return {"status": "success"}, 200
