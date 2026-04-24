class OutputExtractionMixin:
    """
    Mixin que fornece funcionalidades para extração e manipulação de outputs de IA.

    Funcionalidades incluídas:
    - Extração de todos os textos de saída concatenados
    - Extração de texto específico baseado em tipo
    """

    def _extract_all_outputs_in_text(
        self, output: list[dict], separator: str = " "
    ) -> str:
        texts = [
            content.get("text")
            for message in output
            for content in message.get("content", [])
            if "text" in content
        ]

        return separator.join(texts)

    def _extract_output_text(self, response: dict) -> str:
        return next(
            (
                content.get("text")
                for message in response.get("output", [])
                for content in message.get("content", [])
                if "text" in content and content.get("type") == "output_text"
            ),
            "",
        )

    def _extract_specific_output_type(
        self, output: list[dict], output_type: str, separator: str = " "
    ) -> str:
        texts = [
            content.get("text")
            for message in output
            for content in message.get("content", [])
            if "text" in content and content.get("type") == output_type
        ]

        return separator.join(texts)
