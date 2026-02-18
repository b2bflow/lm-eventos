class FunctionCallMixin:
    """
    Mixin que fornece funcionalidades para manipulação de chamadas de função (function calls).

    Funcionalidades incluídas:
    - Processamento de saída de function calls
    - Extração de outputs de function calls completadas
    """

    def _function_call_output(
        self,
        function_call_id: str,
        call_id: str,
        call_name: str,
        arguments: dict,
        input: str | None = None,
    ) -> tuple[list, str, str]:
        if not hasattr(self, "ai"):
            raise AttributeError(
                "Classe deve possuir 'ai' (cliente de IA) para usar FunctionCallMixin"
            )

        if not input and not hasattr(self, "_function_call_input"):
            raise AttributeError(
                "Classe deve possuir '_function_call_input' para usar FunctionCallMixin"
            )

        if not hasattr(self, "model"):
            raise AttributeError(
                "Classe deve possuir 'model' para usar FunctionCallMixin"
            )

        fc_input, response = self.ai.function_call_output(
            function_call_id=function_call_id,
            call_id=call_id,
            call_name=call_name,
            output=input or self._function_call_input,
            arguments=arguments,
            model=self.model,
        )

        all_output = [
            content.get("text")
            for message in response.get("output", [])
            if message.get("status", "") == "completed"
            for content in message.get("content", [])
            if content.get("type") == "output_text"
        ]

        fc_msg_id = response["output"][0]["id"]
        all_output_in_text = ". ".join(all_output) or ""

        return (fc_input, fc_msg_id, all_output_in_text)
