import ast
import mimetypes
import os
import re
from time import sleep
from dotenv import load_dotenv
from typing import Optional, Any
from utils.logger import logger, print_error_details
from utils.phone import is_employee_phone
from chat.repositories.conversation_repository import ConversationRepository
from chat.repositories.message_repository import MessageRepository
from chat.interfaces.chat_service_interface import IMessageService
from ai_agents.clients.openai_client import OpenIAClient
from chat.gateways.adapters.socket_adapter import SocketAdapter
from crm.repositories.customer_repository import CustomerRepository
from gateway.adapters.zapi_adapter import ZAPIClient
from datetime import datetime
from crm.container import CrmContainer
from database.client.mongodb_client import MongoDBClient
from gateway.service.unsupported_media_handler_service import UnsupportedMediaHandlerService
from gateway.service.audio_transcription_service import AudioTranscriptionService
load_dotenv()
class MessageService(IMessageService):
    def __init__(self):
        self.chat = ZAPIClient()
        self.unsupported_media_handler = UnsupportedMediaHandlerService(self.chat, MongoDBClient())
        self.customer_repository = CustomerRepository(MongoDBClient())
        self.message_repo = MessageRepository()
        self.conversation_repo = ConversationRepository()
        self.socket_adapter = SocketAdapter()
        self.phones_for_validation = os.getenv("PHONES_FOR_VALIDATION")
        self.audio_transcription_service = AudioTranscriptionService(self.chat, OpenIAClient())  # Assuming OpenIAClient is properly initialized

    def handle(self, **kwargs) -> dict:
        try:
            phone: str = self.chat.get_phone(**kwargs) or ""
            kwargs["phone"] = phone

            phones_for_validation_list = (
                self.phones_for_validation.split(",") if self.phones_for_validation else []
            )
            # if phones_for_validation_list and phone not in phones_for_validation_list:
            #     return

            # if not self.customer_repository.exists(phone=phone):
            #     self.customer_repository.create(
            #         name=self.chat.get_name(**kwargs), phone=phone
            #     )
            if not self.chat.is_valid_message(**kwargs):
                return

            is_employee = is_employee_phone(phone)
            customer = self.customer_repository.get_by_phone(phone)
            blocked_until = customer.get("blocked_until") if isinstance(customer, dict) else None
            if isinstance(blocked_until, str):
                blocked_until = datetime.fromisoformat(blocked_until.replace("Z", "+00:00"))

            is_blocked = bool(blocked_until and blocked_until.replace(tzinfo=None) > datetime.utcnow())

            if not is_employee and not is_blocked and self.unsupported_media_handler.handle(kwargs):
                return

            message = ""

            if self.chat.is_image(**kwargs):
                caption: str = self.chat.get_image_caption(**kwargs)
                url: str = self.chat.get_image_url(**kwargs)
                message = f"<image-url>{url}</image-url> {caption or ''}"

            elif self.chat.is_file(**kwargs):
                caption: str = self.chat.get_file_caption(**kwargs)
                url: str = self.chat.get_file_url(**kwargs)
                message = f"<file-url>{url}</file-url> {caption or ''}"

            elif self.chat.is_button_response(**kwargs):
                message = f"<kwargs>{kwargs}</kwargs>"

            else:
                transcribed_message = self.audio_transcription_service.transcribe(**kwargs)
                message = transcribed_message or self.chat.get_message(**kwargs)

            return {'phone':phone, 'content':message, 'raw_data':kwargs}

        except Exception as e:
            print_error_details(e)
            logger.error(f"[MessageService] Erro ao processar mensagem: {e}")
            raise e

    def get_messages_by_conversation(self, conversation_id: str):
        try:
            return self.message_repo.get_messages_by_conversation(conversation_id)
        except Exception as e:
            logger.error(f"[MessageService] Erro ao listar mensagens da conversa {conversation_id}: {e}")
            raise e

    def get_messages_by_customer(self, customer_id: str):
        try:
            return self.message_repo.get_messages_by_customer(customer_id)
        except Exception as e:
            logger.error(f"[MessageService] Erro ao listar mensagens do paciente {customer_id}: {e}")
            raise e
        
    def processar_mensagem(self, message) -> list[bool, str | None]:
        # Procura o conteúdo entre <kwargs> e </kwargs>
        print("Mensagem recebida para processamento:")
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
    
    def _determine_agent_flow(self, vals, phone, customer):
        """Define qual agente usar e se deve atualizar tag."""

        if vals[0]:
            if vals[1] == "1" or vals[1] == "13":
                msg_text = "Sobre o que você gostaria de falar? Selecione uma das opções abaixo:"

                buttons = [
                    {"id": "5", "label": "Evento Social"},
                    {"id": "6", "label": "Evento Corporativo"},
                    {"id": "7", "label": "Estrutura Ground/Box Trans"},
                    {"id": "8", "label": "Locação de Produto Único"},
                ]

                self.chat.send_message_with_button(
                    phone=phone, message=msg_text, buttons=buttons
                )

                return True
            
            if vals[1] == "5":
                msg_text = "Qual formato de evento social você deseja realizar? Selecione uma das opções abaixo:"

                buttons = [
                    {"id": "9", "label": "Casamento"},
                    {"id": "10", "label": "Aniversário"},
                    {"id": "11", "label": "Formatura"},
                    {"id": "12", "label": "Debutante"},
                    {"id": "13", "label": "Voltar para menu"},
                ]

                self.chat.send_message_with_button(
                    phone=phone, message=msg_text, buttons=buttons
                )

                return True

            else:
                return False

        return False

    def process_incoming_message(self, phone: str, content: str, external_id: str = None, raw_metadata: dict = None) -> Any:
        try:

            print("Aqui >>>>>>>>>>>> RAW METADATA", raw_metadata)
            print("Aqui >>>>>>>>>>>> Content", content)

            # Verifica se o numero e conteudo sao validos
            if not phone or not content:
                logger.warning("[MessageService] Dados de mensagem recebida incompletos.")
                return None

            customer_service = CrmContainer.get_customer_service()
            quote_service = CrmContainer.get_quote_service()
            customer = customer_service.get_customer_by_phone(phone)

            if not customer:
                logger.info(f"[MessageService] Mensagem de número desconhecido: {phone}. Criando paciente temporário.")
                name = None

                if raw_metadata:
                    name = raw_metadata.get("senderName") or raw_metadata.get("chatName")

                if not name:
                    name = f"WhatsApp {phone}"

                customer = customer_service.register_customer(
                    data={
                        "name": name,
                        "phone": phone
                    }
                )

            blocked_until = customer.get("blocked_until") if isinstance(customer, dict) else None
            if isinstance(blocked_until, str):
                blocked_until = datetime.fromisoformat(blocked_until.replace("Z", "+00:00"))

            is_blocked = bool(blocked_until and blocked_until.replace(tzinfo=None) > datetime.utcnow())
            is_employee = is_employee_phone(phone)

            # 1. Extraimos apenas o ID do dicionario/objeto
            customer_id = customer.get('id') if isinstance(customer, dict) else str(customer.id)
            active_quote = quote_service.get_or_create_active_quote_for_customer(customer_id)

            # 2. Passamos a variavel patient_id para as duas funcoes do repositorio
            conversation = self.conversation_repo.get_active_conversation(customer_id)

            if not conversation:
                conversation = self.conversation_repo.create_conversation(customer_id)

            if active_quote and not getattr(conversation, 'quote', None):
                from crm.models.quote_model import Quote
                conversation.quote = Quote.objects(id=active_quote.get("id")).first()

            message = self._save_and_notify(
                conversation_id=str(conversation.id),
                content=content,
                direction='INCOMING',
                sender_role='user',
                external_id=external_id,
                raw_metadata=raw_metadata
            )

            conversation.updated_at = datetime.now()
            conversation.last_message_content = content
            conversation.unread_count = getattr(conversation, 'unread_count', 0) + 1

            if is_blocked:
                conversation.tag = 'operador_humano'
                conversation.ai_active = False
                conversation.needs_attention = True
            elif getattr(conversation, 'tag', '') in ['OPERADOR', 'operador_humano', 'operador humano', 'orcamento']:
                conversation.needs_attention = True

            self.conversation_repo.update_conversation(conversation)

            if is_blocked:
                logger.info(
                    "[MessageService] Cliente %s bloqueado até %s. Mensagem salva; tag definida como operador_humano e IA não será acionada.",
                    phone,
                    blocked_until,
                )
                return message

            if is_employee:
                logger.info(
                    "[MessageService] Telefone %s está em EMPLOYEE_PHONES. Mensagem salva; IA não será acionada.",
                    phone,
                )
                return message

            if customer.get("new_service", True):
                print(f"Enviando mensagem de boas-vindas para {phone} com ID do paciente {customer.get('id')}")
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

                b = self.customer_repository.update(
                    id=customer.get('id'),
                    attributes={"new_service": False}
                )

                print("Atualização do campo new_service:", b)

                return message
            
            vals = self.processar_mensagem(content)

            leave_execution = self._determine_agent_flow(
                vals, phone, customer)
            
            if leave_execution:
                return message

            if getattr(conversation, 'tag', '') == 'AGENTE' or getattr(conversation, 'ai_active', False):
                from events.tasks import trigger_ai_agent_task
                logger.info(f"[MessageService] Iniciando contagem de Debounce (5s) para IA na conversa {conversation.id}")
                trigger_ai_agent_task.apply_async(args=[str(conversation.id), str(message.id)], countdown=int(os.getenv("DEBOUNCE_SECONDS", 1)))

            return message
        except Exception as e:
            print_error_details(e)
            logger.error(f"[MessageService] Erro ao processar mensagem recebida: {e}")
            raise e

    def _save_and_notify(
        self,
        conversation_id: str,
        content: str,
        direction: str,
        sender_role: str,
        external_id: str = None,
        raw_metadata: dict = None,
        message_type: str = "text",
        media_url: str = None,
        status: str = "QUEUED",
    ) -> Any:
        try:
            conversation = self.conversation_repo.get_by_id(conversation_id)
            if not conversation:
                raise ValueError(f"Conversa {conversation_id} não encontrada para salvar a mensagem.")

            message = self.message_repo.create(
                conversation=conversation,
                direction=direction,
                content=content,
                role=sender_role,
                external_id=external_id,
                raw_metadata=raw_metadata,
                message_type=message_type,
                media_url=media_url,
                status=status,
            )

            self.socket_adapter.emit_new_message({
                "id": str(message.id),
                "conversation_id": conversation_id,
                "content": content,
                "direction": direction,
                "role": sender_role,
                "message_type": message_type,
                "media_url": media_url,
                "raw_metadata": raw_metadata or {},
                "created_at": message.created_at.isoformat()
            })

            return message
        except Exception as e:
            logger.error(f"[MessageService] Falha ao salvar/notificar mensagem: {e}")
            raise e

    def _process_outgoing_message(self, conversation_id: str, content: str, sender_role: str, sender_id: Optional[str] = None):
        try:
            metadata = {"operator_id": sender_id} if sender_id else {}

            message = self._save_and_notify(
                conversation_id=conversation_id,
                content=content,
                direction='OUTGOING',
                sender_role=sender_role,
                raw_metadata=metadata
            )

            conversation = self.conversation_repo.get_by_id(conversation_id)
            if conversation:
                conversation.last_message_content = content
                conversation.updated_at = datetime.now()
                self.conversation_repo.update_conversation(conversation)

            if conversation and hasattr(conversation, 'customer') and getattr(conversation.customer, 'phone', None):
                from events.bus import EventBus
                EventBus.publish("SEND_OUTGOING_MESSAGE", {
                    "phone": conversation.customer.phone,
                    "content": content
                })
                logger.info(f"[MessageService] Evento de envio enfileirado para o telefone {conversation.customer.phone}.")
            else:
                logger.warning(f"[MessageService] Conversa {conversation_id} sem telefone válido. A mensagem não será enviada ao WhatsApp.")

            return message
        except Exception as e:
            logger.error(f"[MessageService] Falha ao processar saída de mensagem: {e}")
            raise e

    def execute_operator_message(self, conversation_id: str, content: str, sender_id: str):
        return self._process_outgoing_message(conversation_id, content, "OPERATOR", sender_id)

    def execute_operator_file(
        self,
        conversation_id: str,
        uploaded_file,
        sender_id: str,
        caption: str | None = None,
    ):
        conversation = self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise ValueError("Conversa não encontrada.")

        if not getattr(conversation, "customer", None) or not getattr(conversation.customer, "phone", None):
            raise ValueError("Conversa sem telefone válido.")

        filename = os.path.basename(getattr(uploaded_file, "name", "arquivo"))
        content_type = (
            getattr(uploaded_file, "content_type", None)
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        size = getattr(uploaded_file, "size", None)
        file_bytes = b"".join(uploaded_file.chunks())

        zapi_response = self.chat.send_file_bytes(
            phone=conversation.customer.phone,
            file_bytes=file_bytes,
            filename=filename,
            content_type=content_type,
            caption=caption,
        )
        send_target = zapi_response.get("send_target", {})
        message_type = send_target.get("message_type", "file")

        external_id = zapi_response.get("messageId") or zapi_response.get("id")
        content = caption or f"[Arquivo] {filename}"
        metadata = {
            "operator_id": sender_id,
            "file_name": filename,
            "content_type": content_type,
            "size": size,
            "send_endpoint": send_target.get("endpoint"),
            "payload_key": send_target.get("payload_key"),
            "zapi_response": zapi_response,
        }

        message = self._save_and_notify(
            conversation_id=conversation_id,
            content=content,
            direction="OUTGOING",
            sender_role="OPERATOR",
            external_id=external_id,
            raw_metadata=metadata,
            message_type=message_type,
            status="SENT_TO_GATEWAY",
        )

        conversation.last_message_content = content
        conversation.updated_at = datetime.now()
        self.conversation_repo.update_conversation(conversation)

        return message

    def execute_bot_message(self, conversation_id: str, content: str):
        return self._process_outgoing_message(conversation_id, content, "assistant")
