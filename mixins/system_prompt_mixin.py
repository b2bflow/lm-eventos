from datetime import datetime
from zoneinfo import ZoneInfo
from utils.logger import logger


hora_sp = datetime.now(ZoneInfo('America/Sao_Paulo'))
hora_utc = hora_sp.astimezone(ZoneInfo('UTC'))

class SystemPromptMixin:
    """
    Mixin que fornece funcionalidades para manipulação de system prompts.

    Funcionalidades incluídas:
    - Inserção de system prompt no contexto
    - Formatação de dados do cliente no prompt
    """

    def _insert_system_prompt(self, customer: dict, input: list) -> list:
        if not hasattr(self, "system_prompt"):
            raise AttributeError(
                "Classe deve possuir 'system_prompt' para usar SystemPromptMixin"
            )

        customer_name = (
            "\n- Nome do cliente: " + customer.get("name").split()[0]
            if customer.get("name")
            else ""
        )

        logger.info(f"[SYSTEM PROMPT MIXIN] Hora atual de são paulo: {hora_utc} {hora_sp}")

        system_prompt = {
            "role": "system",
            "content": self.system_prompt.format(
                current_date=hora_utc,
                customer_name=customer_name,
            ),
        }

        input.insert(
            0,
            system_prompt,
        )

        return input
