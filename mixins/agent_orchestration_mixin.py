import re
import asyncio
from utils.logger import logger


class AgentOrchestrationMixin:
    """
    Mixin que fornece funcionalidades para orquestração de agentes.

    Funcionalidades incluídas:
    - Detecção de triggers de agentes em texto
    - Execução assíncrona de múltiplos agentes
    """

    def _extract_agent_id(self, output: list, all_outputs_in_text: str) -> list[str]:
        pattern = r"#\d+"
        return re.findall(pattern, all_outputs_in_text)

    def _is_agent_trigger(
        self, output: list, all_outputs_in_text: str
    ) -> tuple[bool, list[str]]:
        if not all_outputs_in_text:
            return False, []

        pattern = r"#\d+"
        return (
            bool(re.search(pattern, all_outputs_in_text)),
            self._extract_agent_id(output, all_outputs_in_text),
        )

    async def _handle_agents(
        self, customer: dict, context: list, agent_ids: list[str]
    ) -> list[dict]:
        if not hasattr(self, "agent_container"):
            raise AttributeError(
                "Classe deve possuir 'agent_container' para usar AgentOrchestrationMixin"
            )

        tasks = [
            asyncio.create_task(
                self.agent_container.get(agent_id).execute(
                    customer=customer, context=context
                )
            )
            for agent_id in agent_ids
        ]

        logger.info(f"[AGENT ORCHESTRATION MIXIN] Agente(s) acionado(s): {agent_ids}")

        # Aguarda todas as tasks e pega os resultados
        results = await asyncio.gather(*tasks)

        return results or []
