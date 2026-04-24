import asyncio
import os
import re
from threading import Thread
from datetime import datetime
from ai_agents.interfaces.ai_interface import IAI
from ai_agents.interfaces.tool_interface import ITool
from crm.interfaces.customer_repository_interface import ICustomerRepository
from gateway.interfaces.chat_interface import IChat
from utils.logger import logger, to_json_dump
from ai_agents.mixins.function_call_mixin import FunctionCallMixin


class SummaryTool(ITool, FunctionCallMixin):
    name = "resumo"
    model = "gpt-5.1"
    _function_call_input = "Avise o cliente que logo ele ira receber o seu orçamento, seja educado e cordial."

    def __init__(
        self,
        ai_client: IAI,
        chat_client: IChat,
        customer_repository: ICustomerRepository,
    ):
        self.ai = ai_client
        self.chat = chat_client
        self.customer = customer_repository

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None

        normalized = str(value).strip().replace(" às ", " ").replace(" as ", " ")

        for fmt in (
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue

        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _parse_guest_count(self, value: str | None) -> int:
        if not value:
            return 0

        match = re.search(r"\d+", str(value))
        return int(match.group()) if match else 0

    def _build_notes(self, arguments: dict) -> str:
        lines = []
        for key, value in arguments.items():
            if not value:
                continue
            label = key.replace("_", " ").capitalize()
            lines.append(f"{label}: {value}")
        return "\n".join(lines)

    def _build_customer_attributes(self, customer: dict, arguments: dict) -> dict:
        notes = self._build_notes(arguments)
        next_step = "Preparar orçamento e retorno comercial"

        if "tipo_evento" in arguments:
            return {
                "event_date": self._parse_datetime(arguments.get("data_evento")),
                "guest_count": self._parse_guest_count(arguments.get("numero_pessoas")),
                "celebration_type": arguments.get("tipo_evento"),
                "event_title": arguments.get("tipo_evento"),
                "venue": arguments.get("local_evento"),
                "notes": notes,
                "next_step": next_step,
                "last_interaction_at": datetime.utcnow(),
            }

        if "produto" in arguments:
            produto = arguments.get("produto")
            return {
                "event_date": self._parse_datetime(arguments.get("data_inicio")),
                "celebration_type": "Locação de produto",
                "event_title": produto,
                "venue": arguments.get("local"),
                "notes": notes,
                "next_step": next_step,
                "last_interaction_at": datetime.utcnow(),
            }

        return {
            "notes": notes,
            "next_step": next_step,
            "last_interaction_at": datetime.utcnow(),
        }

    def sends_unregister_request(self, customer_phone: dict, customer_name: str, arguments: dict) -> None:
        phone = os.getenv("REGISTER_PHONE", "").strip()

        lines = ["⚠️ *Nova solicitação* ⚠️\n"]

        for key, value in arguments.items():
            if value:
                label = key.replace("_", " ").capitalize()
                lines.append(f"*{label}*")
                lines.append(f"{value}\n")

        first_message = "\n".join(lines)
        # second_message = "Link para formulario: https://docs.google.com/forms/d/e/1FAIpQLSe5KwuvXlPCKsT1gLtB_0agbidLPTDDueXvqZnMDpB600CDuQ/viewform?pli=1&pli=1"

        self.chat.send_message(
                phone=phone,
                message=first_message,
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

        customer_attributes = self._build_customer_attributes(customer, arguments)

        Thread(
            target=self.sends_unregister_request,
            args=(phone, name, arguments),
            daemon=False,
        ).start()

        tasks = [
            asyncio.to_thread(
                self.customer.update,
                id=customer.get("id"),
                attributes={
                    "new_service": True,
                    "agent": "response_orchestrator",
                    **customer_attributes,
                },
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
