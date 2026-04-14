import ast
from asyncio import sleep
import os
import re

from tomlkit import datetime
from interfaces.agents.agent_interface import IAgent
from interfaces.clients.chat_interface import IChat
from container.agents import AgentContainer
from utils.logger import logger, to_json_dump
from interfaces.repositories.message_repository_interface import IMessageRepository
from interfaces.repositories.customer_repository_interface import ICustomerRepository
from workers.queue_processor import Queue


class GenerateResponseService:

    def __init__(
        self,
        chat_client: IChat,
        message_repository: IMessageRepository,
        customer_repository: ICustomerRepository,
        agents: AgentContainer,
        queue_processor: Queue | None = None,
    ) -> None:
        self.chat = chat_client
        self.message_repository = message_repository
        self.customer_repository = customer_repository
        self.agents = agents
        self.queue = queue_processor

    def _should_abort(self, phone: str) -> bool:
        if self.queue and self.queue.exists(
            phone=phone, status=self.queue.WAITING_STATUS
        ):
            logger.info(
                f"[GENERATE RESPONSE SERVICE] Interrompido geração de resposta para o número {phone}. Pois uma nova mensagem mais recente foi adicionado na fila."
            )
            return True

        return False

    def _resolve_output_content(self, outputs: list | dict) -> str:
        logger.info(
            f"[GENERATE RESPONSE SERVICE] Resolvendo o conteúdo da resposta: \n{to_json_dump(outputs)}"
        )

        return ". ".join(
            (
                output.get("content")
                if isinstance(output.get("content"), str)
                else output.get("content")[0]["text"]
            )
            for output in outputs
            if output.get("role", "") == "assistant"
        )

    def _prepare_context(self, context: list, user_input: str) -> list[dict]:
        # Faz a formatação correta do contexto caso não esteja vazio
        if context:
            context_resolved = []

            # Trata os casos do contexto simples do usuário e do assistente e das chamadas e saídas das tools
            for message in context[::-1]:
                role = message.get("role", "")
                content = message.get("content", "")

                if role in ["user", "assistant"]:
                    context_resolved.append({"role": role, "content": content})
                    continue

                context_resolved.append(content)

            context = context_resolved

        # Prepara o input de imagem caso exista
        image_url = re.search(r"<image-url>(.*?)</image-url>", user_input)
        if image_url:
            user_input = re.sub(
                r"<image-url>.*?</image-url>", "", user_input).strip()
            context.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": user_input,
                        },
                        {
                            "type": "input_image",
                            "image_url": image_url.group(1),
                        },
                    ],
                }
            )

            return context

        # Prepara o input de arquivo caso exista
        file_url = re.search(r"<file-url>(.*?)</file-url>", user_input)
        if file_url:
            user_input = re.sub(r"<file-url>.*?</file-url>",
                                "", user_input).strip()
            context.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": user_input,
                        },
                        {
                            "type": "input_file",
                            "file_url": file_url.group(1),
                        },
                    ],
                }
            )

            return context

        # Caso não tenha imagem, apenas adiciona o input do usuário
        context.append(
            {
                "role": "user",
                "content": str(user_input),
            }
        ),

        return context

    def _save_messages_to_database(
        self, customer: dict, input: dict, outputs: list[dict]
    ) -> None:
        logger.info(
            f"[GENERATE RESPONSE SERVICE] Salvando mensagens no banco de dados para o paciente {customer.get('id')} telefone: {customer.get('phone')}"
        )

        # Salva a nova mensagem do usuário
        content: str | list = input.get("content")
        if content and isinstance(content, list):
            input_text = next(
                (item["text"]
                 for item in content if item.get("type") == "input_text"),
                "",
            )

            input_type = next(
                (
                    item["type"]
                    for item in content
                    if item.get("type") in ["input_image", "input_file"]
                ),
                None,
            )

            self.message_repository.create(
                customer_id=customer.get("id"),
                role=input.get("role"),
                content=f"{input_text} (um {input_type} foi enviado anteriormente)",
            )

        else:
            self.message_repository.create(
                customer_id=customer.get("id"),
                role=input.get("role"),
                content=content,
            )

        if not outputs:
            logger.warning(
                f"[GENERATE RESPONSE SERVICE] A resposta gerada está vazia para o paciente {customer.get('id')} telefone: {customer.get('phone')}. Input: \n{to_json_dump(input)}"
            )
            return

        # Salva a resposta gerada pela IA
        for output in outputs:
            if output.get("type", "") in ["function_call", "function_call_output"]:
                self.message_repository.create(
                    customer_id=customer.get("id"),
                    role=output.get("type"),
                    content=output,
                )
                continue

            self.message_repository.create(
                customer_id=customer.get("id"),
                role=output.get("role"),
                content=output.get("content"),
            )

        logger.info(
            f"[GENERATE RESPONSE SERVICE] Mensagens salvas no banco de dados para o paciente {customer.get('id')} o telefone: {customer.get('phone')}"
        )

    def _get_agent(self, customer: dict) -> IAgent:
        customer_agent = customer.get("agent", "response_orchestrator")
        agent = self.agents.get(id=customer_agent)

        return agent or self.agents.get(id="response_orchestrator")

    def processar_mensagem(self, message) -> list[bool, str | None]:
        # Procura o conteúdo entre <kwargs> e </kwargs>
        match = re.search(r"<kwargs>(.*?)</kwargs>", message, re.DOTALL)

        if match:
            dict_string = match.group(1).strip()

            try:

                kwargs = ast.literal_eval(dict_string)

                btn_resp = kwargs.get("buttonsResponseMessage", {})
                button_id = btn_resp.get("buttonId")

                return [kwargs.get("buttonsResponseMessage"), button_id]

            except (ValueError, SyntaxError) as e:
                print(f"Erro ao converter a string para dicionário: {e}")
        return [False, None]

    def _save_ai_outputs_to_database(self, customer: dict, outputs: list[dict]) -> None:
        if not outputs:
            logger.warning(
                f"[GENERATE RESPONSE SERVICE] A resposta gerada pela IA está vazia para o cliente {customer.get('id')} telefone: {customer.get('phone')}."
            )
            return

        logger.info(
            f"[GENERATE RESPONSE SERVICE] Salvando outputs da IA no banco de dados para o cliente {customer.get('id')} telefone: {customer.get('phone')} \nOutputs: \n{to_json_dump(outputs)}"
        )

        # Salva a resposta gerada pela IA
        for output in outputs:
            if output.get("type", "") in ["function_call", "function_call_output"]:
                self.message_repository.create(
                    customer_id=customer.get("id"),
                    role=output.get("type"),
                    content=output,
                )
                continue

            self.message_repository.create(
                customer_id=customer.get("id"),
                role=output.get("role"),
                content=output.get("content"),
            )

        logger.info(
            f"[GENERATE RESPONSE SERVICE] Outputs da IA salvos com sucesso para o cliente {customer.get('id')}."
        )

    def _save_user_input_to_database(self, customer: dict, input: dict) -> None:
        logger.info(
            f"[GENERATE RESPONSE SERVICE] Salvando input do usuário no banco de dados para o cliente {customer.get('id')} telefone: {customer.get('phone')} \nInput: {to_json_dump(input)}"
        )

        # Salva a nova mensagem do usuário
        content: str | list = input

        if content and isinstance(content, list):
            input_text = next(
                (item["text"]
                 for item in content if item.get("type") == "input_text"),
                "",
            )

            input_type = next(
                (
                    item["type"]
                    for item in content
                    if item.get("type") in ["input_image", "input_file"]
                ),
                None,
            )

            self.message_repository.create(
                customer_id=customer.get("id"),
                role="user",
                content=f"{input_text} (um {input_type} foi enviado anteriormente)",
            )

        else:
            self.message_repository.create(
                customer_id=customer.get("id"),
                role="user",
                content=content,
            )

        logger.info(
            f"[GENERATE RESPONSE SERVICE] Input do usuário salvo com sucesso para o cliente {customer.get('id')}."
        )

    async def _generate_and_send_response(self, agent: IAgent, customer, message, phone):
        """Lógica unificada para gerar, enviar e salvar mensagens."""
        try:

            self._save_user_input_to_database(customer=customer, input=message)

            messages = self.message_repository.get_latest_customer_messages(
                customer_id=customer.get("id"),
                limit=int(os.getenv("CONTEXT_SIZE", 100)),
            )

            context = self._prepare_context(
                context=messages or [],
                user_input=f"{message}.",
            )

            logger.info(
                f"[GENERATE RESPONSE SERVICE] Gerando resposta: {phone}, Agente: {agent.__class__.__name__}"
            )

            full_output = await agent.execute(context=context, customer=customer)
            resolved_content = self._resolve_output_content(full_output)

            # Descomente quando estiver pronto
            self.chat.send_message(phone=phone, message=resolved_content)

            self._save_ai_outputs_to_database(
                customer=customer,
                outputs=full_output,
            )

            logger.info(f"[GENERATE RESPONSE SERVICE] Sucesso para {phone}")

        except Exception as e:
            logger.exception(
                f"[GENERATE RESPONSE SERVICE] ❌ Erro: {to_json_dump(e)}")
            raise e

    def _determine_agent_flow(self, vals, phone, customer):
        """Define qual agente usar e se deve atualizar tag."""
        if vals[0]:
            if vals[1] == "1" or vals[1] == "11":
                msg_text = "Sobre o que você gostaria de falar? Selecione uma das opções abaixo:"

                buttons = [
                    {"id": "5", "label": "Falar com a Erica"},
                    {"id": "6", "label": "Evento Social"},
                    {"id": "7", "label": "Evento Corporativo"},
                    {"id": "8", "label": "Casamento"},
                    {"id": "9", "label": "Estrutura para Eventos"},
                    {"id": "10", "label": "Produto Unico"},
                ]

                self.chat.send_message_with_button(
                    phone=phone, message=msg_text, buttons=buttons
                )

                return self._get_agent(customer=customer), True

            if vals[1] == "5":
                erica_phone = os.getenv("ERICA_PHONE")
                self.chat.send_message(
                    phone=phone, message="Encaminhando para a Erica, aguarde um momento...")

                self.message_repository.create(
                    customer_id=customer.get("id"),
                    role="assistant",
                    content="Encaminhando para a Erica, aguarde um momento...",
                )

                self.chat.send_contact(
                    phone=erica_phone,
                    name=customer.get("name"),
                    contact_phone=phone,
                )

                sleep(2)

                buttons = [
                    {"id": "11", "label": "Sim, quero continuar!"},
                    {"id": "12", "label": "Não, obrigado!"},
                ]

                msg_text = "A Erica já recebeu seu contato e irá falar com você em breve. Enquanto isso, posso ajudar com mais alguma coisa?"

                self.chat.send_message_with_button(
                    phone=phone, message=msg_text, buttons=buttons
                )

                return self._get_agent(customer=customer), True

            else:
                return self._get_agent(customer=customer), False

        return self._get_agent(customer=customer), False

    async def execute(self, phone: str, message: str) -> None:
        customer: dict = self.customer_repository.find(phone=phone)

        customer_follow_up_enabled = customer.get("needs_follow_up")

        if not customer:
            customer = self.customer_repository.create(
                name=self.chat.get_name(phone=phone),
                phone=phone,
            )

        if customer_follow_up_enabled == True:
            self.customer_repository.update(
                id=customer.get("id"), attributes={"needs_follow_up": False}
            )

        automation_enabled = customer.get("automation", True)
        if not automation_enabled:
            logger.info(
                f"[GENERATE RESPONSE SERVICE] Automação desativada para o cliente {customer.get('id')} telefone: {phone}. Ignorando mensagem."
            )
            return

        if customer.get("new_service", True):
            msg_text = "Olá! Bem-vindo à LM Eventos. Sou a Lis. Seu contato é sobre?"

            buttons = [
                {"id": "1", "label": "Solicitar orçamento"},
                {"id": "2", "label": "Financeiro"},
                {"id": "3", "label": "Suporte"},
                {"id": "4", "label": "Outros"},
            ]

            self.chat.send_message_with_button(
                phone=phone, message=msg_text, buttons=buttons
            )

            self.message_repository.create(
                customer_id=customer.get("id"),
                role="assistant",
                content=f"{msg_text} fale com a Erica, Evento Social, Evento Corporativo, Casamento, Estrutura para Eventos, Produto Unico",
            )

            self.customer_repository.update(
                id=customer.get("id"),
                attributes={"new_service": False}
            )

            return

        vals = self.processar_mensagem(message)

        message = vals[0]['message'] if vals[0] else message

        agent, leave_execution = self._determine_agent_flow(
            vals, phone, customer)

        if leave_execution:
            return

        await self._generate_and_send_response(agent, customer, message, phone)
