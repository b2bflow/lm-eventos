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

    def _is_tool_trigger(self, response: dict) -> tuple[bool, list]:
        tools = [
            item
            for item in response.get("output", [])
            if item.get("type") == "function_call" and item.get("status") == "completed"
        ]

        if tools:
            return True, tools

        return False, []

    def _normalize_tool_result(self, result) -> list[dict]:
        if result is None:
            return []

        if isinstance(result, str):
            return [{"role": "assistant", "content": result}]

        if isinstance(result, dict):
            return [result]

        if isinstance(result, list):
            normalized: list[dict] = []
            for item in result:
                if isinstance(item, dict):
                    normalized.append(item)
                elif isinstance(item, str):
                    normalized.append({"role": "assistant", "content": item})
            return normalized

        logger.warning(
            "[TOOL ORCHESTRATION MIXIN] Resultado de tool em formato inesperado: %s",
            type(result).__name__,
        )
        return []

    async def _handle_tools(
        self, customer: dict, context: list, tools: list[dict]
    ) -> list[dict]:
        if not hasattr(self, "tool_container"):
            raise AttributeError(
                "Classe deve possuir 'tool_container' para usar ToolOrchestrationMixin"
            )

        tasks = [
            asyncio.create_task(
                self.tool_container.get(tool.get("name").strip()).execute(
                    function_call_id=tool.get("id"),
                    call_id=tool.get("call_id"),
                    call_name=tool.get("name"),
                    customer=customer,
                    context=context,
                    arguments=json.loads(tool.get("arguments", "{}")),
                )
            )
            for tool in tools
            if tool.get("name")
        ]

        logger.info(
            f"[TOOL ORCHESTRATION MIXIN] Tool(s) acionada(s): {[tool.get('name') for tool in tools]}"
        )

        # Aguarda todas as tasks e pega os resultados
        results = await asyncio.gather(*tasks)

        normalized_results = [self._normalize_tool_result(result) for result in results]

        # Extrai todos os dicionários de cada lista devolvida por cada tool para uma única lista de dicionários
        return [item for sublist in normalized_results for item in sublist]
