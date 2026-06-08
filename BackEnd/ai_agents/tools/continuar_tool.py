import asyncio
from datetime import datetime, timedelta
from os import getenv
import os
from threading import Thread
from chat.interfaces.conversation_repository_interface import IConversationRepository
from chat.repositories import conversation_repository
from ai_agents.interfaces.ai_interface import IAI
from ai_agents.interfaces.tool_interface import ITool
from crm.interfaces.customer_repository_interface import ICustomerRepository
from gateway.interfaces.chat_interface import IChat
from utils.logger import logger, to_json_dump
from ai_agents.mixins.function_call_mixin import FunctionCallMixin


class ContinuarTool(ITool, FunctionCallMixin):
    name = "continuar"
    model = "gpt-5.1"
    _function_call_input = "Avise ao cliente que logo entraremos em contato, seja educado e cordial."

    def __init__(
        self,
        ai_client: IAI,
        chat_client: IChat,
        customer_repository: ICustomerRepository,
        conversation_repository: IConversationRepository,
    ):
        self.ai = ai_client
        self.chat = chat_client
        self.customer = customer_repository
        self.conversation = conversation_repository

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

        self.customer.update(
            id=customer.get("id"),
            attributes={"agent": arguments.get("agent")},
        )

        self.customer.update(
            id=customer.get("id"),
            attributes={"new_service": True}
        )

        self.chat.send_message(
            phone=phone,
            message="Olá eu sou a Liz, atendente da LM Eventos. Para continuarmos, me informe qual seu nome. ",
        )

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

        self.customer.update(
            id=customer.get("id"),
            attributes={"new_service": True}
        )

        return [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "",
                    }
                ],
            },
        ]