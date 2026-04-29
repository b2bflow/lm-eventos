import asyncio
from datetime import datetime

from celery import shared_task
from utils.logger import logger, print_error_details

@shared_task(bind=True, max_retries=3)
def dispatch_event_task(self, event_name: str, payload: dict):
    logger.info(f"[EventTasks] Processando evento na fila: {event_name}")
    try:
        from events.bus import EventBus
        EventBus.handle_event(event_name, payload)
        return f"Event {event_name} processed"
    except Exception as e:
        logger.error(f"[EventTasks] Falha ao processar evento {event_name}: {e}")
        self.retry(exc=e, countdown=10)

@shared_task(bind=True)
def trigger_ai_agent_task(self, conversation_id: str, trigger_message_id: str):
    try:
        from chat.container import ChatContainer
        from ai_agents.container import AgentsContainer
        conversation_service = ChatContainer.get_conversation_service()
        message_service = ChatContainer.get_message_service()

        conversation = conversation_service.conversation_repo.get_by_id(conversation_id)

        if not conversation:
            return "Conversa não encontrada"

        blocked_until = getattr(conversation.customer, "blocked_until", None)
        if blocked_until and blocked_until.replace(tzinfo=None) > datetime.utcnow():
            logger.info(
                "[EventTasks] Abortando IA para conversa %s. Cliente bloqueado até %s.",
                conversation_id,
                blocked_until,
            )
            return "Blocked"

        recent_messages = message_service.message_repo.get_recent_context(conversation_id, limit=1)

        if not recent_messages:
            logger.warning(f"[EventTasks] Nenhuma mensagem encontrada para a conversa {conversation_id}.")
            return "Sem mensagens"

        last_message = recent_messages[0]

        # Verificar se a logica está verificando se não foi recebida uma nova mensagem após a original que disparou a task
        if str(last_message.id) != trigger_message_id:
            logger.info(f"[Debounce] Abortando resposta para {conversation_id}. Nova mensagem detetada após a original.")
            return "Debounced"

        logger.info(f"[Debounce] Tempo esgotado para {conversation_id}. Iniciando Orquestrador de IA...")
        orchestrator = AgentsContainer.get_orchestrator()
        phone = conversation.customer.phone
        message_content = last_message.content

        asyncio.run(orchestrator.execute(phone=phone, message=message_content))
        return "Processado"

    except Exception as e:
        print_error_details(e)
        logger.error(f"[EventTasks] Falha na task da IA para conversa {conversation_id}: {e}")
