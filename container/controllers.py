from controllers.process_automation_controller import ProcessController
from controllers.process_incoming_message_controller import (
    ProcessIncomingMessageController,
)
from container.services import ServiceContainer


class ControllerContainer:

    def __init__(self, services: ServiceContainer):
        self._services = services

    @property
    def process_incoming_message_controller(self) -> ProcessIncomingMessageController:
        return ProcessIncomingMessageController(
            message_queue_service=self._services.message_queue_service,
        )
    
    @property
    def process_controller(self) -> ProcessController:
        return ProcessController(
            service=self._services.automation_service
        )

