import os
import re
from datetime import datetime
from ai_agents.interfaces.agent_interface import IAgent
from gateway.interfaces.chat_interface import IChat
from ai_agents.containers.agent_container import AgentContainer
from chat.interfaces.conversation_repository_interface import IConversationRepository
from chat.interfaces.chat_service_interface import IMessageService
from utils.logger import logger, to_json_dump
from chat.interfaces.message_repository_interface import IMessageRepository
from crm.interfaces.customer_repository_interface import ICustomerRepository
import re
from chat.container import ChatContainer
class GenerateResponseService:

    def __init__(
        self,
        chat_client: IChat,
        message_repository: IMessageRepository,
        customer_repository: ICustomerRepository,
        conversation_repository: IConversationRepository,
        agents: AgentContainer,
        # message_service: IMessageService,
    ) -> None:

        self.chat = chat_client
        self.message_repository = message_repository
        self.customer_repository = customer_repository
        self.agents = agents
        self.conversation_repository = conversation_repository
        # self.messages_service = message_service

        self.message_container = ChatContainer()
        self.message_service = self.message_container.get_message_service()

    def _normalize_message_content(self, content):
        if isinstance(content, str):
            return content

        if content is None:
            return ""

        if isinstance(content, list):
            normalized_items = []
            for item in content:
                if not isinstance(item, dict):
                    continue

                normalized_item = dict(item)

                if "text" in normalized_item and normalized_item["text"] is not None:
                    normalized_item["text"] = str(normalized_item["text"])

                if "image_url" in normalized_item and normalized_item["image_url"] is not None:
                    normalized_item["image_url"] = str(normalized_item["image_url"])

                if "file_url" in normalized_item and normalized_item["file_url"] is not None:
                    normalized_item["file_url"] = str(normalized_item["file_url"])

                normalized_items.append(normalized_item)

            return normalized_items

        return str(content)

    def _content_as_text(self, content) -> str:
        normalized_content = self._normalize_message_content(content)

        if isinstance(normalized_content, str):
            return normalized_content.strip()

        if isinstance(normalized_content, list):
            text_parts = [
                item.get("text", "").strip()
                for item in normalized_content
                if isinstance(item, dict) and item.get("text")
            ]
            return " ".join(part for part in text_parts if part).strip()

        return str(normalized_content).strip()

    def _message_already_in_context(self, context: list[dict], user_input: str) -> bool:
        if not context:
            return False

        latest_user_message = next(
            (
                message
                for message in reversed(context)
                if isinstance(message, dict) and message.get("role") == "user"
            ),
            None,
        )

        if not latest_user_message:
            return False

        latest_content = self._content_as_text(latest_user_message.get("content"))
        current_input = self._content_as_text(user_input)

        return bool(latest_content) and latest_content == current_input

    def _resolve_output_content(self, outputs: list | dict) -> str:
        logger.info(
            f"[GENERATE RESPONSE SERVICE] Resolvendo o conteúdo da resposta: \n{to_json_dump(outputs)}"
        )

        if isinstance(outputs, str):
            return outputs

        if isinstance(outputs, dict):
            outputs = [outputs]

        if not isinstance(outputs, list):
            logger.warning(
                "[GENERATE RESPONSE SERVICE] Saída em formato inesperado: %s",
                type(outputs).__name__,
            )
            return ""

        resolved_outputs: list[str] = []

        for output in outputs:
            if isinstance(output, str):
                resolved_outputs.append(output)
                continue

            if not isinstance(output, dict):
                logger.warning(
                    "[GENERATE RESPONSE SERVICE] Item de saída ignorado por formato inválido: %s",
                    type(output).__name__,
                )
                continue

            if output.get("role", "") != "assistant":
                continue

            content = output.get("content")

            if isinstance(content, str):
                resolved_outputs.append(content)
                continue

            if isinstance(content, list):
                text_parts = [
                    item.get("text", "")
                    for item in content
                    if isinstance(item, dict) and item.get("text")
                ]
                if text_parts:
                    resolved_outputs.append(" ".join(text_parts))

        return ". ".join(item for item in resolved_outputs if item)

    def _prepare_context(self, context: list, user_input: str) -> list[dict]:
        # Faz a formatação correta do contexto caso não esteja vazio
        if context:
            context_resolved = []

            # Trata os casos do contexto simples do usuário e do assistente e das chamadas e saídas das tools
            for message in context:
                role = message.get("role", "")
                content = message.get("content", "")

                if role in ["user", "assistant"]:
                    context_resolved.append(
                        {
                            "role": role,
                            "content": self._normalize_message_content(content),
                        }
                    )
                    continue

                context_resolved.append(content)

            context = context_resolved

        # Prepara o input de imagem caso exista
        image_url = re.search(r"<image-url>(.*?)</image-url>", user_input)
        if image_url:
            user_input = re.sub(r"<image-url>.*?</image-url>", "", user_input).strip()
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
            user_input = re.sub(r"<file-url>.*?</file-url>", "", user_input).strip()
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
        if not self._message_already_in_context(context, user_input):
            context.append(
                {
                    "role": "user",
                    "content": str(user_input),
                }
            )

        return context

    def _remove_links(self, message: str) -> str:
        pattern = r'\[.*?\]\(https?://cepsbrasil\.com\.br[^\)]*\)|https?://cepsbrasil\.com\.br\S*|cepsbrasil\.com\.br\S*'

        clean = re.sub(pattern, '', message)
        return clean

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
                (item["text"] for item in content if item.get("type") == "input_text"),
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

            # self.message_repository.create(
            #     customer_id=customer.get("id"),
            #     role=input.get("role"),
            #     content=f"{input_text} (um {input_type} foi enviado anteriormente)",
            # )
            conversation = self.conversation_repository.get_active_conversation(customer=customer)

            print(conversation.to_json())

        else:
            conversation = self.conversation_repository.get_active_conversation(customer=customer)

            print(conversation.to_json())

            # conversation: ConversationModel,
            # direction: str,
            # content: str,
            # role: str = None,
            # status: str = 'QUEUED',
            # external_id: str = None,
            # raw_metadata: dict = None
            # self.message_repository.create(
            #     customer_id=customer.get("id"),
            #     role=input.get("role"),
            #     content=content,
            # )

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
        agent = customer.get("agent")

        print(f"Aqui >>>>>>>>>>>>>>>>>>>>>, {customer}")
        return self.agents.get(agent)

    async def execute(self, phone: str, message: str) -> None:
        customer: dict = self.customer_repository.find(phone=phone)

        if not customer:
            customer = self.customer_repository.create(
                name=self.chat.get_name(phone=phone),
                phone=phone,
                agent="response_orchestrator",
            )

        blocked_until = customer.get("blocked_until")
        if isinstance(blocked_until, str):
            blocked_until = datetime.fromisoformat(blocked_until.replace("Z", "+00:00"))

        if blocked_until and blocked_until.replace(tzinfo=None) > datetime.utcnow():
            logger.info(
                "[GENERATE RESPONSE SERVICE] Cliente %s bloqueado até %s. IA não processada.",
                phone,
                blocked_until,
            )
            return

        active_conversation = self.conversation_repository.get_active_conversation(customer=customer.get("id"))
        if active_conversation:
            messages = [
                msg.to_dict()
                for msg in self.message_repository.get_recent_context(
                    str(active_conversation.id),
                    limit=int(os.getenv("CONTEXT_SIZE", "100")),
                )
            ]
        else:
            messages: list = self.message_repository.get_latest_customer_messages(
                customer_id=customer.get("id"), limit=int(os.getenv("CONTEXT_SIZE", "100"))
            )

        context: list[dict] = self._prepare_context(
            context=messages or [],
            user_input=message,
        )

        agent = self._get_agent(customer=customer)

        logger.info(
            f"[GENERATE RESPONSE SERVICE] Gerando resposta para o número: {phone}, Agente: {agent.__class__.__name__}"
        )

        try:
            full_output: list[dict] = await agent.execute(
                context=context, customer=customer
            )

            resolved_output_content = self._resolve_output_content(full_output)

            self.chat.send_message(
                phone=phone,
                message=self._remove_links(resolved_output_content).replace("()", ""),
            )

            conversation = self.conversation_repository.get_active_conversation(customer=customer.get('id'))

            self.message_service._save_and_notify(
                conversation_id=str(conversation.id),
                content=resolved_output_content,
                direction="OUTGOING",
                sender_role="assistant"
            )

            # self._save_messages_to_database(
            #     customer=customer,
            #     input=context[-1],
            #     outputs=full_output,
            # )

            logger.info(
                f"[GENERATE RESPONSE SERVICE] Resposta final: \ninput: {to_json_dump(context[-1])} \noutput: {to_json_dump(resolved_output_content)}"
            )

        except Exception as e:
            logger.exception(
                f"[GENERATE RESPONSE SERVICE] ❌ Erro ao gerar resposta: \n{to_json_dump(e)}"
            )

            raise e
