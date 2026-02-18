from os import getenv
from interfaces.tools.tool_interface import ITool
from interfaces.clients.ai_interface import IAI
from interfaces.clients.chat_interface import IChat
from utils.logger import logger, to_json_dump
from mixins.function_call_mixin import FunctionCallMixin


class ExampleTool(ITool, FunctionCallMixin):
    name = "name"
    model = "gpt-4.1"
    _function_call_input = "Avise o cliente..."

    def __init__(
        self,
        ai_client: IAI,
        chat_client: IChat,
    ):
        self.ai = ai_client
        self.chat = chat_client

    async def execute(
        self,
        function_call_id: str,
        call_id: str,
        call_name: str,
        customer: dict,
        context: list,
        arguments: dict,
    ) -> list[dict]:
        phone: str = customer.get("phone")

        logger.info(
            "[SCHEDULE TOOL] Executando a ferramenta '%s', telefone: %s, function_call_id: %s, call_id: %s, call_name: %s, arguments: %s",
            self.__class__.__name__,
            phone,
            function_call_id,
            call_id,
            call_name,
            to_json_dump(arguments),
        )

        fc_input, fc_msg_id, function_call_output = self._function_call_output(
            function_call_id=function_call_id,
            call_id=call_id,
            call_name=call_name,
            arguments=arguments,
        )

        return [
            *fc_input,
            {
                "id": fc_msg_id,
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": function_call_output,
                    }
                ],
            },
        ]
