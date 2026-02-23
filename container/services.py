from container.clients import ClientContainer
from container.repositories import RepositoryContainer
from container.agents import AgentContainer
from container.tools import ToolContainer
from interfaces.clients.chat_interface import IChat
from services.automation_service import AutomationService
from services.message_queue_service import MessageQueueService
from services.generate_response_service import GenerateResponseService
from services.audio_transcription_service import AudioTranscriptionService
from services.unsupported_media_handler_service import UnsupportedMediaHandlerService
from services.automation_is_paused_service import AutomationIsPausedService
from workers.queue_processor import Queue


class ServiceContainer:

    def __init__(
        self,
        clients: ClientContainer,
        repositories: RepositoryContainer,
        agents: AgentContainer,
        tools: ToolContainer,
        queue_processor: Queue,
    ):
        self._clients = clients
        self._repositories = repositories
        self.agents = agents
        self.tools = tools
        self._queue_processor = queue_processor

    @property
    def generate_response_service(self) -> GenerateResponseService:
        return GenerateResponseService(
            chat_client=self._clients.chat,
            message_repository=self._repositories.message,
            customer_repository=self._repositories.customer,
            agents=self.agents,
            queue_processor=self._queue_processor,
        )

    @property
    def message_queue_service(self) -> MessageQueueService:
        return MessageQueueService(
            cache_client=self._clients.cache,
            chat_client=self._clients.chat,
            unsupported_media_handler=self.unsupported_media_handler_service,
            audio_transcription_service=self.audio_transcription_service,
            automation_is_paused_service=self.automation_is_paused_service,
            customer_repository=self._repositories.customer,
        )

    @property
    def audio_transcription_service(self) -> AudioTranscriptionService:
        return AudioTranscriptionService(
            chat_client=self._clients.chat,
            ai_client=self._clients.ai,
        )

    @property
    def unsupported_media_handler_service(self) -> UnsupportedMediaHandlerService:
        return UnsupportedMediaHandlerService(
            chat_client=self._clients.chat,
            database_client=self._clients.database,
        )

    @property
    def automation_is_paused_service(self):
        return AutomationIsPausedService(
            chat_client=self._clients.chat,
        )

    @property
    def automation_service(self) -> AutomationService:
        return AutomationService(
            customer_repository=self._repositories.customer,
            manager_repository=self._repositories.manager,
            chat_client=self._clients.chat
        )