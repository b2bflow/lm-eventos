from ai_agents.tools.humano_tool import HumanoTool
from ai_agents.tools.summary_tool import SummaryTool
from ai_agents.interfaces.tool_interface import ITool

from functools import partial
from typing import Callable
from ai_agents.containers.client_container import ClientContainer
from ai_agents.containers.repository_container import RepositoryContainer

from ai_agents.tools.human_transfer_tool import HumanTransferTool



class ToolContainer:

    def __init__(
        self,
        clients: ClientContainer,
        repositories: RepositoryContainer,
        agents,
    ):
        self._clients = clients
        self._repositories = repositories
        self._factories: dict[str, Callable[[], ITool]] = {}
        self._agents = agents
        self._register_tools()

    def _register_tools(self):
        self._factories = {
            "human_transfer_tool": partial(
                HumanTransferTool,
                client_container=self._clients,
                repository_container=self._repositories,
                agent_container=self._agents,
            ),

            "resumo": partial(
                SummaryTool,
                ai_client=self._clients.ai(),
                chat_client=self._clients.chat(),
                customer_repository=self._repositories.customer,
                conversation_repository=self._repositories.conversation,
            ),

            "humano": partial(
                HumanoTool,
                ai_client=self._clients.ai(),
                chat_client=self._clients.chat(),
                customer_repository=self._repositories.customer,
            ),
        }

    def get(self, name: str) -> ITool:
        
        factory = self._factories[name]
        return factory()

    def all(self) -> list[ITool]:
        return [factory() for factory in self._factories.values()]
