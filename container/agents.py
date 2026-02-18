from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Callable
from interfaces.agents.agent_interface import IAgent
from container.clients import ClientContainer
from container.repositories import RepositoryContainer
import agents
import pkgutil
import importlib

if TYPE_CHECKING:
    from container.tools import ToolContainer


class AgentContainer:
    _clients: ClientContainer
    _repositories: RepositoryContainer
    _tools: ToolContainer | None
    _agent_factories: dict[str, Callable[[], IAgent]]
    _initialized: bool

    def __init__(
        self,
        clients: ClientContainer,
        repositories: RepositoryContainer,
        tools: ToolContainer | None = None,
    ) -> None:
        self._clients = clients
        self._repositories = repositories
        self._tools = tools
        self._agent_factories = {}
        self._initialized = False
        if self._tools is not None:
            self._register_agents()

    def set_tools(self, tools: ToolContainer) -> None:
        self._tools = tools
        if not self._initialized:
            self._register_agents()

    def _register_agents(self) -> None:
        if self._initialized:
            return
        if self._tools is None:
            return

        for _, module_name, _ in pkgutil.iter_modules(agents.__path__):
            module = importlib.import_module(f"agents.{module_name}")
            for attr in dir(module):
                obj = getattr(module, attr)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, IAgent)
                    and hasattr(obj, "factory")
                ):
                    factory_method = obj.factory
                    agent_factory = partial(
                        factory_method,
                        agent_container=self,
                        tool_container=self._tools,
                        client_container=self._clients,
                        repository_container=self._repositories,
                    )

                    # Instancia uma vez para obter o ID e validar
                    agent = agent_factory()

                    if agent:
                        if agent.id in self._agent_factories:
                            raise ValueError(f"Duplicate agent ID found: {agent.id}")

                        # Armazena a factory, não a instância
                        self._agent_factories[agent.id] = agent_factory
        self._initialized = True

    def get(self, id: str) -> IAgent | None:
        """Cria uma nova instância do agent sob demanda com as dependências injetadas"""
        factory = self._agent_factories.get(id)
        if factory is None:
            return None
        return factory()

    def all(self) -> list[IAgent]:
        """Cria novas instâncias de todos os agents"""
        return [factory() for factory in self._agent_factories.values()]
