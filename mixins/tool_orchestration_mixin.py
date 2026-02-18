import asyncio
import json
from utils.logger import logger


class ToolOrchestrationMixin:
    """
    Mixin que fornece funcionalidades para orquestração de tools/funções.

    Funcionalidades incluídas:
    - Detecção de triggers de tools em resposta da IA
    - Execução assíncrona de múltiplas tools
    """

    def _is_tool_trigger(self, response: dict) -> tuple[bool, dict | None]:
        tool = next(
            (
                output
                for output in response.get("output", [])
                if output.get("type", "") == "function_call"
            ),
            None,
        )

        if tool:
            return True, tool

        return False, None

    async def _handle_tool(
        self, customer: dict, context: list, tool: dict
    ) -> list[dict]:
        if not hasattr(self, "tool_container"):
            raise AttributeError(
                "Classe deve possuir 'tool_container' para usar ToolOrchestrationMixin"
            )

        if not tool:
            raise ValueError("Tool inválida fornecida para execução")

        logger.info(f"[TOOL ORCHESTRATION MIXIN] Tool acionada: {tool.get('name')}")

        return await asyncio.create_task(
            self.tool_container.get(tool.get("name").strip()).execute(
                function_call_id=tool.get("id"),
                call_id=tool.get("call_id"),
                call_name=tool.get("name"),
                customer=customer,
                context=context,
                arguments=json.loads(tool.get("arguments", "{}")),
            )
        )
