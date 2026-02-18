from __future__ import annotations

from container.clients import ClientContainer
from container.services import ServiceContainer
from container.controllers import ControllerContainer
from container.repositories import RepositoryContainer
from container.agents import AgentContainer
from container.tools import ToolContainer
from workers.queue_processor import Queue


class Container:
    def __init__(self):
        self.clients: ClientContainer = ClientContainer()

        self.repositories: RepositoryContainer = RepositoryContainer(
            clients=self.clients
        )

        self.agents: AgentContainer = AgentContainer(
            clients=self.clients, repositories=self.repositories, tools=None
        )

        self.tools: ToolContainer = ToolContainer(
            clients=self.clients, repositories=self.repositories, agents=self.agents
        )

        self.agents.set_tools(self.tools)

        self.queue = Queue(
            cache_client=self.clients.cache,
            generate_response_service=None,
        )

        self.services = ServiceContainer(
            clients=self.clients,
            repositories=self.repositories,
            agents=self.agents,
            tools=self.tools,
            queue_processor=self.queue,
        )

        self.queue.set_generate_response_service(
            self.services.generate_response_service
        )

        self.controllers = ControllerContainer(services=self.services)
