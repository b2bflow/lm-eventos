"""Ações da equipe na aba WhatsApp: retomar a IA ou assumir a conversa, atribuir a SDR, Erica ou
Lúcia, nota interna e registro de ligação.

Cada ação deixa uma mensagem interna na conversa (direction INTERNAL, hidden_from_ai) para a
equipe ver quem fez o quê; ela nunca vai para o cliente nem entra no histórico da IA. Também
fica registrada na linha do tempo do card (ServiceLog).
"""
from datetime import datetime

from bson import ObjectId

from chat.models.conversation_model import ConversationModel
from crm.repositories.log_service_repository import ServiceLogRepository

ASSIGNEES = {'sdr': 'SDR', 'erica': 'Erica', 'lucia': 'Lúcia'}


def user_display_name(user) -> str:
    if user is None:
        return "Sistema"
    full = f"{getattr(user, 'first_name', '') or ''} {getattr(user, 'last_name', '') or ''}".strip()
    return full or getattr(user, 'username', None) or "Usuário"


def _operator_id(user) -> str | None:
    return str(user.id) if user is not None and getattr(user, 'id', None) else None


def _get(conversation_id: str) -> ConversationModel:
    try:
        conversation = ConversationModel.objects(id=ObjectId(conversation_id)).first()
    except Exception:
        conversation = None
    if not conversation:
        raise ValueError("Conversa não encontrada.")
    return conversation


class ConversationHandoverService:

    def _internal(self, conversation: ConversationModel, text: str, kind: str, user=None) -> None:
        from chat.container import ChatContainer
        ChatContainer.get_message_service()._save_and_notify(
            conversation_id=str(conversation.id), content=text, direction='INTERNAL',
            sender_role='note' if kind == 'note' else 'system', message_type=kind, hidden_from_ai=True,
            raw_metadata={"operator_id": _operator_id(user), "operator_name": user_display_name(user)},
            status='RECEIVED',
        )

    # --- IA x humano ---------------------------------------------------------------------

    def set_mode(self, conversation_id: str, mode: str, user=None) -> ConversationModel:
        """mode AGENTE (retomar IA) ou OPERADOR (assumir). Registra quem fez e quando."""
        if mode not in ('AGENTE', 'OPERADOR'):
            raise ValueError("Modo inválido. Use AGENTE ou OPERADOR.")
        conversation = _get(conversation_id)
        customer = conversation.customer
        if mode == 'AGENTE' and customer and customer.human_operator:
            raise ValueError("Contato de parceiro fica com a Erica: a IA não atende este contato.")
        if conversation.tag == mode and conversation.ai_active == (mode == 'AGENTE'):
            return conversation

        name = user_display_name(user)
        now = datetime.utcnow()
        conversation.tag = mode
        conversation.ai_active = mode == 'AGENTE'
        if mode == 'AGENTE':
            conversation.needs_attention = False
        conversation.handover_by = _operator_id(user)
        conversation.handover_at = now
        conversation.updated_at = now
        conversation.save()

        text = (f"IA retomada por {name}. A assistente responde a partir da próxima mensagem do cliente."
                if mode == 'AGENTE' else f"Atendimento assumido por {name}. IA pausada nesta conversa.")
        self._internal(conversation, text, 'event', user)
        if customer:
            ServiceLogRepository.create_log(
                customer=customer, operator_id=_operator_id(user), action_type='HANDOVER',
                description=text.split(".")[0] + ".", metadata={"conversation_id": str(conversation.id), "mode": mode},
            )
        return conversation

    # --- Atribuição ----------------------------------------------------------------------

    def assign(self, conversation_id: str, assignee: str | None, user=None) -> ConversationModel:
        assignee = assignee or None
        if assignee is not None and assignee not in ASSIGNEES:
            raise ValueError("Responsável inválido. Use sdr, erica ou lucia.")
        conversation = _get(conversation_id)
        if conversation.assignee == assignee:
            return conversation
        conversation.assignee = assignee
        conversation.updated_at = datetime.utcnow()
        conversation.save()
        target = ASSIGNEES[assignee] if assignee else "ninguém"
        text = f"Conversa atribuída a {target} por {user_display_name(user)}."
        self._internal(conversation, text, 'event', user)
        if conversation.customer:
            ServiceLogRepository.create_log(
                customer=conversation.customer, operator_id=_operator_id(user), action_type='CONVERSATION_ASSIGNED',
                description=text, metadata={"conversation_id": str(conversation.id), "assignee": assignee},
            )
        return conversation

    # --- Nota interna e ligação ----------------------------------------------------------

    def add_note(self, conversation_id: str, text: str, user=None) -> dict:
        text = (text or "").strip()
        if not text:
            raise ValueError("A nota não pode ficar vazia.")
        conversation = _get(conversation_id)
        self._internal(conversation, text, 'note', user)
        from crm.container import CrmContainer
        return CrmContainer.get_pipeline_service().add_note(str(conversation.customer.id), text, user=user)

    def log_call(self, conversation_id: str, outcome: str, notes: str | None = None, user=None) -> dict:
        conversation = _get(conversation_id)
        from crm.container import CrmContainer
        from crm.services.pipeline_service import CALL_OUTCOMES
        log = CrmContainer.get_pipeline_service().log_call(str(conversation.customer.id), outcome, notes, user=user)
        text = f"Ligação registrada por {user_display_name(user)}: {CALL_OUTCOMES[outcome]}."
        if notes:
            text += f" {notes.strip()}"
        self._internal(conversation, text, 'event', user)
        return log
