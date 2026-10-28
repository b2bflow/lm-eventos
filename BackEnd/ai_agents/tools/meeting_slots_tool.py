from datetime import datetime

from agenda.services.free_slots import MEETING_MINUTES, describe_slot, next_free_slots
from ai_agents.tools.summary_tool import SummaryTool
from utils.logger import logger, to_json_dump

# Palavra usada em "todos os detalhes do seu ___" a partir do tipo de evento que a IA coletou.
EVENT_WORDS = {
    "casamento": "casamento", "aniversario": "aniversário", "aniversário": "aniversário",
    "formatura": "formatura", "debutante": "evento", "15 anos": "evento", "festa": "evento",
}


def _event_word(event_type: str | None) -> str:
    text = (event_type or "").strip().lower()
    for key, word in EVENT_WORDS.items():
        if key in text:
            return word
    return "evento"


def build_meeting_message(customer_name: str | None, event_type: str | None, slots: list[datetime],
                          now: datetime | None = None) -> str:
    """Mensagem do Marcelo (reunião de 28/10): reunião de 40 minutos com o time técnico em um de dois
    horários livres da agenda. Sem horário livre, pergunta o melhor dia e horário."""
    first = (customer_name or "").split(" ")[0]
    greeting = f"Perfeito, {first}." if first and not first.startswith("WhatsApp") else "Perfeito."
    word = _event_word(event_type)
    article = "da" if word == "formatura" else "do"
    text = (
        f"{greeting} Pelo que você me passou, a gente consegue te atender. Estamos analisando o seu pedido e "
        f"gostaríamos de agendar uma reunião de {MEETING_MINUTES} minutos entre você e o nosso time técnico para "
        f"entender todos os detalhes {article} seu {word} e te entregar o melhor orçamento possível."
    )
    if len(slots) >= 2:
        options = f"{describe_slot(slots[0], now)} ou {describe_slot(slots[1], now)}"
        return f"{text} Se nos organizarmos para falar {options}, você consegue?"
    if slots:
        return f"{text} Se nos organizarmos para falar {describe_slot(slots[0], now)}, você consegue?"
    return f"{text} Qual o melhor dia e horário para você?"


class MeetingSlotsTool(SummaryTool):
    """Fim da qualificação de evento social ou corporativo: em vez de "logo você recebe o orçamento", a IA
    oferece dois horários livres da agenda para uma reunião com o time técnico e sai da conversa.

    A resposta do cliente fica com a equipe (a IA já está pausada): ela confirma o horário e agenda a
    reunião pela plataforma, o que leva o card para "Reunião agendada". O lead entra no funil como
    "Lead qualificado" (via cotação em WAITING_BUDGET) e o grupo de atendimento é avisado.
    """

    name = "oferecer_horarios"

    async def execute(
        self,
        function_call_id: str,
        call_id: str,
        call_name: str,
        customer: dict,
        context: list,
        arguments: dict,
    ) -> list[dict]:
        logger.info(
            "[MEETING SLOTS TOOL] Cliente %s qualificado, argumentos: %s",
            customer.get("phone"),
            to_json_dump(arguments),
        )

        now = datetime.utcnow()
        slots = next_free_slots(now=now)
        offered = " ou ".join(describe_slot(s, now) for s in slots)

        customer_attributes = self._build_customer_attributes(customer, arguments)
        customer_attributes["next_step"] = (
            f"Confirmar a reunião de {MEETING_MINUTES} min oferecida pela IA: {offered}" if offered
            else f"Combinar com o cliente o horário da reunião de {MEETING_MINUTES} min"
        )
        customer_attributes["status"] = "WAITING_BUDGET"

        # A IA sai da conversa: a resposta com o horário vai para a equipe agendar.
        self._block_customer_and_mark_budget(customer)
        self.customer.update(
            id=customer.get("id"),
            attributes={"new_service": True, "agent": "response_orchestrator", "next_step": customer_attributes["next_step"]},
        )
        # Cotação em WAITING_BUDGET: lead qualificado pela IA, no funil e aviso no grupo de atendimento.
        active_quote = self.quote_service.get_or_create_active_quote_for_customer(
            customer_id=customer.get("id"),
            seed=customer_attributes,
        )
        if active_quote:
            self.quote_service.update_quote(quote_id=active_quote.get("id"), data=customer_attributes)

        message = build_meeting_message(customer.get("name"), arguments.get("tipo_evento"), slots, now)
        return [{"role": "assistant", "content": message}]
