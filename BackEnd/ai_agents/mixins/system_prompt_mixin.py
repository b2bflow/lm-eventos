from datetime import datetime


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

        customer_name = customer.get("name", "").split()[0] if customer.get("name") else ""

        system_prompt = {
            "role": "developer",
            "content": self.system_prompt.format(
                current_date=datetime.now().strftime("%A %Y/%m/%d %H:%M"),
                customer_name=customer_name,
            ),
        }

        input.insert(
            0,
            system_prompt,
        )

        return input
