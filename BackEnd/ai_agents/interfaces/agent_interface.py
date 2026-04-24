from abc import ABC, abstractmethod
from ai_agents.clients.openai_client import OpenIAClient

class IAgent(ABC):

    def __init__(
        self,
        agent_container,
        tool_container,
        message_repository,
        ai_client: OpenIAClient,
    ) -> None:
        self.agent_container = agent_container
        self.tool_container = tool_container
        self.message_repository = message_repository
        self.ai = ai_client

    @property
    @abstractmethod
    def id(self) -> str | None:
        return None

    @property
    @abstractmethod
    def model(self) -> str: ...

    @property
    def instructions(self) -> str | None:
        return None

    @property
    def name(self) -> str | None:
        return None

    @property
    def description(self) -> str | None:
        return None

    @property
    @abstractmethod
    def system_prompt(self) -> str | None:
        return None

    @property
    def tools(self) -> list:
        return []

    @staticmethod
    @abstractmethod
    def factory(
        agent_container,
        tool_container,
        client_container,
        repository_container,
    ) -> "IAgent": ...

    @abstractmethod
    async def execute(self, context: list, customer: dict) -> list[dict]: ...
