import asyncio
from os import getenv
import os
from threading import Thread
from interfaces.tools.tool_interface import ITool
from interfaces.clients.ai_interface import IAI
from interfaces.clients.chat_interface import IChat
from interfaces.repositories.customer_repository_interface import ICustomerRepository
from utils.logger import logger, to_json_dump
from mixins.function_call_mixin import FunctionCallMixin


class SummaryTool(ITool, FunctionCallMixin):
    name = "resumo"
    model = "gpt-5.1"
    _function_call_input = "Avise o cliente que um colaborador responsavel dará continuidade ao atendimento."

    def __init__(
        self,
        ai_client: IAI,
        chat_client: IChat,
        customer_repository: ICustomerRepository,
    ):
        self.ai = ai_client
        self.chat = chat_client
        self.customer = customer_repository

    def sends_unregister_request(self, customer_phone: dict, customer_name: str, arguments: dict) -> None:
        phone = os.getenv("REGISTER_PHONE", "").strip()
        
        lines = ["⚠️ *Nova solicitação* ⚠️\n"]
        
        for key, value in arguments.items():
            if value:
                label = key.replace("_", " ").capitalize()
                lines.append(f"*{label}*")
                lines.append(f"{value}\n")

        first_message = "\n".join(lines)
        second_message = "Link para formulario: https://docs.google.com/forms/d/e/1FAIpQLSe5KwuvXlPCKsT1gLtB_0agbidLPTDDueXvqZnMDpB600CDuQ/viewform?pli=1&pli=1"

        message = [first_message, second_message]

        for msg in message:
            self.chat.send_message(
                phone=phone,
                message=msg,
            )

        self.chat.send_contact(
            phone=phone,
            name=customer_name,
            contact_phone=customer_phone or "",
        )


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
        name: str = customer.get("name")

        logger.info(
            "[UNREGISTER TOOL] Executando a ferramenta '%s', telefone: %s, function_call_id: %s, call_id: %s, call_name: %s, arguments: %s",
            self.__class__.__name__,
            phone,
            function_call_id,
            call_id,
            call_name,
            to_json_dump(arguments),
        )

        logger.info(
            "[UNREGISTER TOOL] Argumentos: %s",
            arguments,
        )


        Thread(
            target=self.sends_unregister_request,
            args=(phone, name, arguments),
            daemon=False,
        ).start()

        tasks = [
            asyncio.to_thread(
                self.customer.update,
                id=customer.get("id"),
                attributes={"agent": "response_orchestrator"},
            ),
            asyncio.to_thread(
                self._function_call_output,
                function_call_id=function_call_id,
                call_id=call_id,
                call_name=call_name,
                arguments=arguments,
            ),
        ]

        _, (fc_input, fc_msg_id, function_call_output) = await asyncio.gather(*tasks)

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
