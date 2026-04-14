from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Callable
from interfaces.tools.tool_interface import ITool
from container.clients import ClientContainer
from container.repositories import RepositoryContainer
from tools.agent_transfer_tool import AgentTransferTool
from tools.humano_tool import HumanoTool
from tools.summary_tool import SummaryTool


if TYPE_CHECKING:
    from container.agents import AgentContainer


class ToolContainer:
    def __init__(
        self,
        clients: ClientContainer,
        repositories: RepositoryContainer,
        agents: AgentContainer,
    ) -> None:
        self._clients: ClientContainer = clients
        self._repositories: RepositoryContainer = repositories
        self._factories: dict[str, Callable[[], ITool]] = {}
        self._agents: AgentContainer = agents
        self._register_tools()

    def _register_tools(self) -> None:
        agent_transfer_factory = partial(
            AgentTransferTool,
            customer_repository=self._repositories.customer,
            agent_container=self._agents,
        )

        self._factories = {
            "agent": agent_transfer_factory,
            
            "orquestrador": agent_transfer_factory,

            "resumo": partial(
                SummaryTool,
                ai_client=self._clients.ai,
                chat_client=self._clients.chat,
                customer_repository=self._repositories.customer,
            ),

            "humano": partial(
                HumanoTool,
                ai_client=self._clients.ai,
                chat_client=self._clients.chat,
                customer_repository=self._repositories.customer,
            )
        }

    def get(self, name: str) -> ITool:
        """Cria uma nova instância da tool sob demanda com as dependências injetadas"""
        factory = self._factories[name]
        return factory()

    def all(self) -> list[ITool]:
        """Cria novas instâncias de todas as tools"""
        return [factory() for factory in self._factories.values()]
