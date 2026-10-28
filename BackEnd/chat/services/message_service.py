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
from chat.repositories.system_config_repository import SystemConfigRepository
from chat.interfaces.chat_service_interface import IMessageService
from ai_agents.clients.openai_client import OpenIAClient
from chat.gateways.adapters.socket_adapter import SocketAdapter
from crm.repositories.customer_repository import CustomerRepository
from gateway.adapters.zapi_adapter import ZAPIClient
from datetime import datetime, timedelta
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

            external_id = kwargs.get("messageId") or kwargs.get("id")
            return {'phone':phone, 'content':message, 'external_id':external_id, 'raw_data':kwargs}

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
        match = re.search(r"<kwargs>(.*?)</kwargs>", message, re.DOTALL)

        if match:
            dict_string = match.group(1).strip()

            try:

                kwargs = ast.literal_eval(dict_string)

                btn_resp = kwargs.get("buttonsResponseMessage", {})
                button_id = btn_resp.get("buttonId")

                return [kwargs.get("buttonsResponseMessage"), button_id]

            except (ValueError, SyntaxError) as e:
                logger.warning(f"[MessageService] Erro ao converter a string para dicionário: {e}")
        return [False, None]
    
    def _determine_agent_flow(self, vals, phone, customer, conversation=None):
        """Define qual agente usar e se deve atualizar tag."""

        if vals[0]:
            if vals[1] == "1" or vals[1] == "13":
                msg_text = "Sobre o que você gostaria de falar? Selecione uma das opções abaixo:"

                buttons = [
                    {"id": "5", "label": "Evento Social"},
                    {"id": "6", "label": "Evento Corporativo"},
                    {"id": "7", "label": "Estrutura Ground/Box Truss"},
                    {"id": "8", "label": "Locação de Produto Único"},
                ]

                self.chat.send_message_with_button(
                    phone=phone, message=msg_text, buttons=buttons
                )
                self._record_menu_message(conversation, msg_text, buttons)

                self.customer_repository.update(
                    id=customer.get('id'),
                    attributes={
                        "send_button": False,
                        "last_message_attendant": datetime.now(),
                    }
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
                self._record_menu_message(conversation, msg_text, buttons)

                self.customer_repository.update(
                    id=customer.get("id"),
                    attributes={
                        "last_message_attendant": datetime.now(),
                    },
                )

                return True

            elif vals[1] == "3":
                msg_text = (
                    "Esse é o grupo central de oportunidades. Sempre que surgir uma vaga, "
                    "publicamos por aqui para buscar os melhores profissionais para a posição. "
                    "Fique à vontade para entrar e acompanhar!\n\n"
                    "https://chat.whatsapp.com/G2JH9A0kp9O6ErGDlOyVlI?s=cl&p=i&ilr=2&amv=0"
                )
                self.chat.send_message(phone=phone, message=msg_text)
                self._record_menu_message(conversation, msg_text)

                customer_id = customer.get('id') if isinstance(customer, dict) else str(customer.id)
                self.customer_repository.update(
                    id=customer_id,
                    attributes={
                        "send_button": True,
                        "new_service": True,
                        "agent": "response_orchestrator",
                        "silenced_until": datetime.now() + timedelta(minutes=5)
                    }
                )

                conversation = self.conversation_repo.get_active_conversation(customer_id)
                if conversation:
                    conversation.ai_active = False
                    conversation.tag = 'vagas'
                    conversation.status = 'CLOSED'
                    self.conversation_repo.update_conversation(conversation)

                return True

            else:
                customer_id = customer.get('id') if isinstance(customer, dict) else str(customer.id)
                
                if customer.get("name_collected", False):
                    self.customer_repository.update(
                        id=customer_id,
                        attributes={"send_button": False}
                    )
                    return False

                conversation = self.conversation_repo.get_active_conversation(customer_id)
                if conversation:
                    self._process_outgoing_message(
                        conversation_id=str(conversation.id),
                        content="Antes de continuarmos, qual o seu nome, por favor?",
                        sender_role="assistant"
                    )

                self.customer_repository.update(
                    id=customer_id,
                    attributes={
                        "send_button": False,
                        "waiting_for_name": True
                    }
                )

                return True

        return False

    def process_incoming_message(self, phone: str, content: str, external_id: str = None, raw_metadata: dict = None) -> Any:
        try:
            # Verifica se o numero e conteudo sao validos
            if not phone or not content:
                logger.warning("[MessageService] Dados de mensagem recebida incompletos.")
                return None

            if external_id:
                from chat.models.message_model import MessageModel
                if MessageModel.objects(external_id=external_id).first():
                    logger.info(f"[MessageService] Mensagem com external_id {external_id} já processada. Ignorando duplicata.")
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

            silenced_until = customer.get("silenced_until") if isinstance(customer, dict) else None
            if isinstance(silenced_until, str):
                silenced_until = datetime.fromisoformat(silenced_until.replace("Z", "+00:00"))

            is_silenced = bool(silenced_until and silenced_until.replace(tzinfo=None) > datetime.utcnow())

            # 1. Extraimos apenas o ID do dicionario/objeto
            customer_id = customer.get('id') if isinstance(customer, dict) else str(customer.id)

            if customer.get("waiting_for_name", False):
                customer = self.customer_repository.update(
                    id=customer_id,
                    attributes={
                        "name": content,
                        "waiting_for_name": False,
                        "name_collected": True
                    }
                )

            active_quote = quote_service.get_or_create_active_quote_for_customer(customer_id)

            # 2. Passamos a variavel patient_id para as duas funcoes do repositorio
            conversation = self.conversation_repo.get_active_conversation(customer_id)

            if not conversation:
                conversation = self.conversation_repo.create_conversation(customer_id)
                if customer.get("human_operator"):
                    # Parceiro ou cliente antigo (regra 1): fica com a Erica, sem IA e sem menu.
                    conversation.tag = 'OPERADOR'
                    conversation.ai_active = False
                    self.conversation_repo.update_conversation(conversation)

            if active_quote and not getattr(conversation, 'quote', None):
                from crm.models.quote_model import Quote
                conversation.quote = Quote.objects(id=active_quote.get("id")).first()

            message_type, media_url = self._extract_media(raw_metadata)
            message = self._save_and_notify(
                conversation_id=str(conversation.id),
                content=content,
                direction='INCOMING',
                sender_role='user',
                external_id=external_id,
                raw_metadata=raw_metadata,
                message_type=message_type,
                media_url=media_url,
                status='RECEIVED',
            )

            conversation.updated_at = datetime.now()
            conversation.last_message_content = self._preview(content, message_type, raw_metadata)
            conversation.unread_count = getattr(conversation, 'unread_count', 0) + 1

            if is_blocked:
                conversation.tag = 'operador_humano'
                conversation.ai_active = False
                conversation.needs_attention = True
            elif getattr(conversation, 'tag', '') in ['OPERADOR', 'operador_humano', 'operador humano', 'orcamento']:
                conversation.needs_attention = True

            self.conversation_repo.update_conversation(conversation)
            self._touch_customer_interaction(customer_id)

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

            if is_silenced:
                logger.info(
                    "[MessageService] Cliente %s silenciado até %s. Mensagem salva; IA não será acionada.",
                    phone,
                    silenced_until,
                )
                return message

            # Chave "IA ativa globalmente" (Configurações > Integrações): desligada, ninguém recebe resposta automática.
            if not SystemConfigRepository.get_config().ai_active:
                logger.info("[MessageService] IA desligada globalmente. Mensagem de %s salva; IA não será acionada.", phone)
                return message

            should_trigger_ai = (
                getattr(conversation, "status", "") == "OPEN"
                and getattr(conversation, "tag", "") == "AGENTE"
                and getattr(conversation, "ai_active", False) is True
            )

            if not should_trigger_ai:
                logger.info(
                    "[MessageService] Mensagem salva para %s; IA não acionada. Status=%s Tag=%s AI=%s.",
                    phone,
                    getattr(conversation, "status", None),
                    getattr(conversation, "tag", None),
                    getattr(conversation, "ai_active", None),
                )
                return message

            if self.customer_repository.claim_new_service(customer_id):
                logger.info(f"[MessageService] Enviando mensagem de boas-vindas para {phone} com ID do cliente {customer_id}")
                msg_text = "Olá bem vindo, a LM Eventos, me chamo Marcelo e vou dar início ao seu atendimento. Seu contato é sobre?"

                buttons = [
                    {"id": "1", "label": "Solicitar orçamento"},
                    {"id": "2", "label": "Financeiro"},
                    {"id": "3", "label": "Vaga de emprego"},
                    {"id": "4", "label": "Outros"},
                ]

                self.customer_repository.update(
                    id=customer_id,
                    attributes={
                        "last_message_attendant": datetime.now(),
                    },
                )

                self.chat.send_message_with_button(
                    phone=phone, message=msg_text, buttons=buttons
                )
                self._record_menu_message(conversation, msg_text, buttons)

                return message
            
            vals = self.processar_mensagem(content)

            leave_execution = self._determine_agent_flow(
                vals, phone, customer, conversation)
            
            if leave_execution:
                return message
            
            if customer.get("send_button", True):
                last_attendant = customer.get("last_message_attendant")
                if isinstance(last_attendant, str):
                    try:
                        last_attendant = datetime.fromisoformat(last_attendant.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        last_attendant = None

                # Se a mensagem com opções foi enviada há menos de 10 segundos, não reenvia o aviso enquanto o usuário digita
                if last_attendant and (datetime.utcnow() - last_attendant).total_seconds() < 10:
                    logger.info(f"[MessageService] Menu enviado recentemente para {phone}. Ignorando reenvio imediato do aviso de opções.")
                    return message

                msm_text = "Por favor, para que eu possa te ajudar melhor, selecione uma das opções enviadas anteriormente."

                self.chat.send_message(
                    phone=phone, 
                    message=msm_text
                )
                self._record_menu_message(conversation, msm_text)

                return message

            if should_trigger_ai:
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
        hidden_from_ai: bool = False,
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
                hidden_from_ai=hidden_from_ai,
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
                "buttons": (raw_metadata or {}).get("buttons") if direction == 'OUTGOING' else None,
                "author_name": (raw_metadata or {}).get("operator_name") if direction == 'INTERNAL' else None,
                "created_at": message.created_at.isoformat()
            })

            return message
        except Exception as e:
            logger.error(f"[MessageService] Falha ao salvar/notificar mensagem: {e}")
            raise e

    @staticmethod
    def _extract_media(raw_metadata: dict | None) -> tuple[str, str | None]:
        """Tipo e URL da mídia a partir do payload da Z-API (o content continua como a IA lê hoje)."""
        from utils.safe_url import safe_media_url
        data = raw_metadata or {}
        for kind, key, url_key in (("image", "image", "imageUrl"), ("file", "document", "documentUrl"),
                                   ("audio", "audio", "audioUrl")):
            if isinstance(data.get(key), dict) and data[key].get(url_key):
                # URL fora de http(s) não vai para o painel (o content da IA continua igual).
                return kind, safe_media_url(data[key][url_key])
        return "text", None

    @staticmethod
    def _preview(content: str, message_type: str, raw_metadata: dict | None) -> str:
        """Texto curto da última mensagem para a lista de conversas."""
        data = raw_metadata or {}
        if message_type == "image":
            caption = (data.get("image") or {}).get("caption")
            return f"[Imagem] {caption}".strip() if caption else "[Imagem]"
        if message_type == "file":
            doc = data.get("document") or {}
            return f"[Arquivo] {doc.get('fileName') or doc.get('caption') or ''}".strip()
        if message_type == "audio":
            return f"[Áudio] {content}".strip()
        if isinstance(data.get("buttonsResponseMessage"), dict):
            return data["buttonsResponseMessage"].get("message") or content
        return content

    def _record_menu_message(self, conversation, content: str, buttons: list | None = None):
        """Registra na conversa uma mensagem do menu já enviada pela Z-API (fora do contexto da IA)."""
        if not conversation:
            return None
        try:
            metadata = {"menu": True}
            if buttons:
                metadata["buttons"] = buttons
            message = self._save_and_notify(
                conversation_id=str(conversation.id),
                content=content,
                direction='OUTGOING',
                sender_role='assistant',
                raw_metadata=metadata,
                hidden_from_ai=True,
                status='SENT_TO_GATEWAY',
            )
            conversation.last_message_content = content
            self.conversation_repo.update_conversation(conversation)
            return message
        except Exception as e:
            # O menu já foi enviado ao cliente; falha ao registrar não pode interromper o fluxo.
            logger.error(f"[MessageService] Falha ao registrar mensagem do menu: {e}")
            return None

    def _touch_customer_interaction(self, customer_id: str):
        try:
            self.customer_repository.update(id=customer_id, attributes={"last_interaction_at": datetime.utcnow()})
        except Exception as e:
            logger.error(f"[MessageService] Falha ao atualizar última interação do cliente {customer_id}: {e}")

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

        from chat.services.chat_file_service import public_base_url, save_chat_file, signed_file_url

        filename = os.path.basename(getattr(uploaded_file, "name", "") or "") or "arquivo"
        content_type = (
            getattr(uploaded_file, "content_type", None)
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        size = getattr(uploaded_file, "size", None)
        if not size:
            raise ValueError("Arquivo vazio.")

        # Guardado antes de enviar: a conversa mostra o arquivo e a Z-API baixa os grandes pelo link.
        chat_file = save_chat_file(conversation, uploaded_file, filename, content_type)
        file_url = signed_file_url(chat_file)

        # Base64 dentro do JSON infla 33% e pesa na Z-API: acima do limite vai o link público.
        inline_max = int(os.getenv("CHAT_FILE_INLINE_MAX_MB", "10")) * 1024 * 1024
        if size > inline_max and public_base_url():
            zapi_response = self.chat.send_file(
                phone=conversation.customer.phone,
                file=file_url,
                filename=filename,
                content_type=content_type,
                caption=caption,
            )
        else:
            uploaded_file.seek(0)
            zapi_response = self.chat.send_file_bytes(
                phone=conversation.customer.phone,
                file_bytes=b"".join(uploaded_file.chunks()),
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
            "chat_file_id": str(chat_file.id),
            "send_endpoint": send_target.get("endpoint"),
            "payload_key": send_target.get("payload_key"),
            "zapi_response": zapi_response,
        }
        if message_type == "file":
            metadata["document"] = {"documentUrl": file_url, "fileName": filename}

        message = self._save_and_notify(
            conversation_id=conversation_id,
            content=content,
            direction="OUTGOING",
            sender_role="OPERATOR",
            external_id=external_id,
            raw_metadata=metadata,
            message_type=message_type,
            media_url=file_url,
            status="SENT_TO_GATEWAY",
        )

        conversation.last_message_content = content
        conversation.updated_at = datetime.now()
        self.conversation_repo.update_conversation(conversation)

        return message

    def execute_bot_message(self, conversation_id: str, content: str):
        return self._process_outgoing_message(conversation_id, content, "assistant")
