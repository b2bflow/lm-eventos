import os
from interfaces.clients.cache_interface import ICache
from interfaces.clients.chat_interface import IChat
from utils.logger import logger
from services.unsupported_media_handler_service import UnsupportedMediaHandlerService
from services.audio_transcription_service import AudioTranscriptionService
from services.automation_is_paused_service import AutomationIsPausedService
from interfaces.repositories.customer_repository_interface import ICustomerRepository
from workers.queue_processor import Queue


class MessageQueueService:

    def __init__(
        self,
        cache_client: ICache,
        chat_client: IChat,
        unsupported_media_handler: UnsupportedMediaHandlerService,
        audio_transcription_service: AudioTranscriptionService,
        automation_is_paused_service: AutomationIsPausedService,
        customer_repository: ICustomerRepository,
    ) -> None:
        self.cache = cache_client
        self.chat = chat_client
        self.unsupported_media_handler = unsupported_media_handler
        self.audio_transcription_service = audio_transcription_service
        self.automation_is_paused_service = automation_is_paused_service
        self.customer_repository = customer_repository
        self.phones_for_validation = os.getenv("PHONES_FOR_VALIDATION")

    def handle(self, **kwargs) -> None:
        phone: str = self.chat.get_phone(**kwargs) or ""
        kwargs["phone"] = phone

        phones_for_validation_list = (
            self.phones_for_validation.split(",") if self.phones_for_validation else []
        )

        if phones_for_validation_list and phone not in phones_for_validation_list:
            logger.info(
                f"[MESSAGE QUEUE SERVICE] Número {phone} não está na lista de validação. Mensagem não adicionada a fila.",
                phone,
            )

            return

        if self.automation_is_paused_service.check(phone=phone):
            return

        if not self.customer_repository.exists(phone=phone):
            self.customer_repository.create(
                name=self.chat.get_name(**kwargs), phone=phone
            )

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

        else:
            transcribed_message = self.audio_transcription_service.transcribe(**kwargs)
            message = transcribed_message or self.chat.get_message(**kwargs)

        queue_key = os.getenv("QUEUE_KEY")
        Queue.enqueue(
            cache_client=self.cache,
            queue_key=queue_key,
            key=phone,
            value=message,
            append=True,
        )

        logger.info(
            f"[MESSAGE QUEUE SERVICE] Adicionado mensagem para o número {phone} na fila {queue_key}. Mensagem: {message!r}"
        )
