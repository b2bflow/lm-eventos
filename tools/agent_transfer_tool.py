from interfaces.tools.tool_interface import ITool
from interfaces.repositories.customer_repository_interface import ICustomerRepository
from container.agents import AgentContainer


class AgentTransferTool(ITool):
    name = "Agent Transfer Tool"
    model = "gpt-4.1"

    def __init__(
        self,
        customer_repository: ICustomerRepository,
        agent_container: AgentContainer,
    ):
        self.customer_repository = customer_repository
        self.agent = agent_container

    async def execute(
        self,
        function_call_id: str,
        call_id: str,
        call_name: str,
        customer: dict,
        context: list,
        arguments: dict,
    ) -> list[dict]:
        agent: str = arguments.get("agent", "response_orchestrator")

        attributes = {
            "agent": agent,
        }

        if customer.get("name") != attributes.get("name"):
            attributes["name"] = arguments.get("customer_name", customer.get("name"))

        self.customer_repository.update(
            id=customer.get("id"),
            attributes=attributes,
        )

        return await self.agent.get(agent).execute(
            context=context,
            customer=customer,
        )
