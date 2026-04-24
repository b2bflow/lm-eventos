from typing import Dict, Any
from ai_agents.mixins.agent_orchestration_mixin import AgentOrchestrationMixin
from ai_agents.mixins.function_call_mixin import FunctionCallMixin
from ai_agents.containers.repository_container import RepositoryContainer
from ai_agents.containers.client_container import ClientContainer
from utils.logger import logger
from ai_agents.interfaces.tool_interface import ITool



class HumanTransferTool(ITool, FunctionCallMixin, AgentOrchestrationMixin):
    name = "human_transfer_tool"
    model = "gpt-5.1"
    _function_call_input = ""

    def __init__(
        self,
        client_container: ClientContainer,
        repository_container: RepositoryContainer,
        agent_container,
    ):
        self._client_container = client_container
        self._repository_container = repository_container
        self._agents = agent_container
    @property
    def name(self) -> str:
        return "human_transfer_tool"

    @property
    def schema(self) -> Dict[str, Any]:
        return (
            {
                "type": "function",
                "name": "human_transfer_tool",
                "description": "Encaminha o atendimento para um humano",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "nome_completo": {
                            "description": "Nome completo do cliente",
                            "type": "string",
                        }
                    },
                    "required": ["nome_completo"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        )

    async def execute(self, **kwargs) -> list[dict]:
        try:
            logger.info(f"EXECUTOU FUNCTION HUMAN TRANSFER TOOL {kwargs}")

            self._repository_container.customer.update(
                id=kwargs['customer'].get('id'),
                attributes={
                    "agent": kwargs['arguments']['agent']
                }
            )

            logger.info("AGENTE ENCONTRADO: ", self._agents.get(kwargs['arguments']['agent']))

            result = await self._agents.get(kwargs['arguments']['agent']).execute(
                kwargs['context'], kwargs['customer']
            )

            if isinstance(result, str):
                return [{"role": "assistant", "content": result}]

            if isinstance(result, dict):
                return [result]

            return result

        except Exception as e:
            logger.error(f"[HumanTransferTool] Falha crítica na execução da ferramenta: {e}")
            return [
                {
                    "role": "assistant",
                    "content": "Erro interno ao processar o atendimento.",
                }
            ]
