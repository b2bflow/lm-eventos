from typing import Dict, Any

from ai_agents.mixins.agent_orchestration_mixin import AgentOrchestrationMixin
from ai_agents.mixins.function_call_mixin import FunctionCallMixin
from ai_agents.containers.repository_container import RepositoryContainer
from ai_agents.containers.client_container import ClientContainer
from utils.logger import logger
from ai_agents.interfaces.tool_interface import ITool


class HumanTransferTool(ITool, FunctionCallMixin, AgentOrchestrationMixin):
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
        return {
            "type": "function",
            "name": "human_transfer_tool",
            "description": "Encaminha o atendimento para outro agente",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent": {
                        "description": "Identificador do agente que receberá o atendimento",
                        "type": "string",
                    }
                },
                "required": ["agent"],
                "additionalProperties": False,
            },
            "strict": True,
        }

    def _clean_agent_context(self, context: list) -> list:
        """
        Remove prompts de system/developer do agente anterior.
        Mantém apenas o histórico real da conversa.
        """

        allowed_roles = {
            "user",
            "assistant",
            "tool",
            "function",
        }

        return [
            message
            for message in context
            if message.get("role") in allowed_roles
        ]

    async def execute(self, **kwargs) -> list[dict]:
        try:
            logger.info(
                "[HUMAN_TRANSFER_TOOL] Executando transferência: %s",
                kwargs,
            )

            target_agent = kwargs["arguments"]["agent"]

            self._repository_container.customer.update(
                id=kwargs["customer"].get("id"),
                attributes={
                    "agent": target_agent,
                },
            )

            clean_context = self._clean_agent_context(
                kwargs.get("context", [])
            )

            logger.info(
                "[HUMAN_TRANSFER_TOOL] Contexto limpo enviado para %s: %s",
                target_agent,
                clean_context,
            )

            result = await self._agents.get(target_agent).execute(
                clean_context,
                kwargs["customer"],
            )

            if isinstance(result, str):
                return [
                    {
                        "role": "assistant",
                        "content": result,
                    }
                ]

            if isinstance(result, dict):
                return [result]

            return result

        except Exception as e:
            logger.exception(
                "[HumanTransferTool] Falha crítica na execução da ferramenta"
            )

            return [
                {
                    "role": "assistant",
                    "content": "Erro interno ao processar o atendimento.",
                }
            ]