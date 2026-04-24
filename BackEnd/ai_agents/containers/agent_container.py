from __future__ import annotations
from typing import TYPE_CHECKING, Callable
from ai_agents.interfaces.agent_interface import IAgent
from ai_agents.clients.openai_client import OpenIAClient
from ai_agents.containers.repository_container import RepositoryContainer
from ai_agents.containers.tool_container import ToolContainer
from functools import partial
from typing import Callable
from ai_agents import agents
import pkgutil
import importlib


if TYPE_CHECKING:
    from ai_agents.containers.client_container import ClientContainer

class AgentContainer:
    _clients: ClientContainer
    _repositories: RepositoryContainer
    _tools: ToolContainer | None
    _agent_factories: dict[str, Callable[[], IAgent]]
    _initialized: bool

    def __init__(
        self,
        clients: OpenIAClient,
        repositories: RepositoryContainer,
        tools: ToolContainer,
    ) -> None:
        self._clients = clients
        self._repositories = repositories
        self._tools = tools
        self._factories: dict[str, Callable[[], IAgent]] = {}
        self._agents_ids: list[str] = []
        self._initialized = False
        self._register_agents()

    def set_tools(self, tools: ToolContainer) -> None:
        self._tools = tools
        if not self._initialized:
            self._register_agents()

    def _register_agents(self):
        for _, module_name, _ in pkgutil.iter_modules(agents.__path__):
            module = importlib.import_module(f"ai_agents.agents.{module_name}")
            for attr in dir(module):
                obj = getattr(module, attr)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, IAgent)
                    and hasattr(obj, "factory")
                ):
                    # Criar uma instância temporária para obter o ID
                    temp_agent = obj.factory(
                        agent_container=self,
                        tool_container=self._tools,
                        client_container=self._clients,
                        repository_container=self._repositories,
                    )

                    if temp_agent:
                        agent_id = temp_agent.id

                        # if agent_id in self._agents_ids:
                        #     raise ValueError(f"Duplicate agent ID found: {agent_id}")

                        self._agents_ids.append(agent_id)

                        # Registrar o factory como partial
                        self._factories[agent_id] = partial(
                            obj.factory,
                            agent_container=self,
                            tool_container=self._tools,
                            client_container=self._clients,
                            repository_container=self._repositories,
                        )

    def get(self, id: str) -> IAgent | None:
        factory = self._factories.get(id)
        return factory() if factory else None

    def all(self) -> list[IAgent]:
        return [factory() for factory in self._factories.values()]
