import ast
import os
import re
from time import sleep
from dotenv import load_dotenv
from typing import Optional, Any
from utils.logger import logger, print_error_details
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
            if phones_for_validation_list and phone not in phones_for_validation_list:
                return

            # if not self.customer_repository.exists(phone=phone):
            #     self.customer_repository.create(
            #         name=self.chat.get_name(**kwargs), phone=phone
            #     )
            if not self.chat.is_valid_message(**kwargs):
                return

            if self.unsupported_media_handler.handle(kwargs):
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

        print("entrou aquii pohhaa")

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

                return True

            if vals[1] == "5":
                erica_phone = os.getenv("ERICA_PHONE")
                self.chat.send_message(
                    phone=phone, message="Encaminhando para a Erica, aguarde um momento...")

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

                self.message_repo.create(
                    role="assistant",
                    content=msg_text,
                    direction="OUTGOING",
                    conversation=None,
                    raw_metadata={"buttons": buttons}
                )

                return True

            else:
                return False

        return False

    def process_incoming_message(self, phone: str, content: str, external_id: str = None, raw_metadata: dict = None) -> Any:
        try:

            print("Aqui >>>>>>>>>>>> RAW METADATA", raw_metadata)
            print("Aqui >>>>>>>>>>>> Content", content)

            # Verifica se o numro e conteudo são validos
            if not phone or not content:
                logger.warning("[MessageService] Dados de mensagem recebida incompletos.")
                return None

            customer_service = CrmContainer.get_customer_service()
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

                return
            
            vals = self.processar_mensagem(content)

            message = vals[0]['message'] if vals[0] else content

            leave_execution = self._determine_agent_flow(
                vals, phone, customer)
            
            if leave_execution:
                return

            # 1. Extraímos apenas o ID do dicionário/objeto
            customer_id = customer.get('id') if isinstance(customer, dict) else str(customer.id)

            # 2. Passamos a variável patient_id para as duas funções do repositório
            conversation = self.conversation_repo.get_active_conversation(customer_id)

            if not conversation:
                conversation = self.conversation_repo.create_conversation(customer_id)

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

            if getattr(conversation, 'tag', '') == 'OPERADOR':
                conversation.needs_attention = True

            self.conversation_repo.update_conversation(conversation)

            if getattr(conversation, 'tag', '') == 'AGENTE' or getattr(conversation, 'ai_active', False):
                from events.tasks import trigger_ai_agent_task
                logger.info(f"[MessageService] Iniciando contagem de Debounce (5s) para IA na conversa {conversation.id}")
                trigger_ai_agent_task.apply_async(args=[str(conversation.id), str(message.id)], countdown=int(os.getenv("DEBOUNCE_SECONDS", 1)))

            return message
        except Exception as e:
            print_error_details(e)
            logger.error(f"[MessageService] Erro ao processar mensagem recebida: {e}")
            raise e

    def _save_and_notify(self, conversation_id: str, content: str, direction: str, sender_role: str, external_id: str = None, raw_metadata: dict = None) -> Any:
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
                raw_metadata=raw_metadata
            )

            self.socket_adapter.emit_new_message({
                "id": str(message.id),
                "conversation_id": conversation_id,
                "content": content,
                "direction": direction,
                "role": sender_role,
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

    def execute_bot_message(self, conversation_id: str, content: str):
        return self._process_outgoing_message(conversation_id, content, "assistant")