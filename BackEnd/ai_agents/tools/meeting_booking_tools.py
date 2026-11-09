"""Agendamento da reunião com o time técnico pela IA (social e corporativo), pedido do João em 06/11.

Depois de `oferecer_horarios`, a conversa fica com o agente `meeting_agent`, que usa estas ferramentas:

- `agendar_reuniao`: o cliente aceitou um dos horários ou disse um horário dele. Livre -> a reunião é
  marcada na agenda da Erica (o cliente recebe a confirmação da agenda) e a conversa passa para a equipe.
- `oferecer_outros_horarios`: o cliente só pode num período (manhã/tarde/noite) ou num dia -> dois
  horários livres dentro disso.
- `perguntar_horario`: o cliente não pode nos horários (ou no dia) e não disse outro -> pergunta qual
  horário (ou qual dia e horário) é melhor.

Tentativas: a oferta inicial é a 1ª. A IA tem só mais uma (pergunta extra, outros horários ou "esse horário
não está livre"). Se o cliente ainda não conseguir marcar, a conversa vai para a equipe. A contagem fica no
código (Customer.meeting_offer["round"]), não no prompt.
"""
from datetime import date, datetime, timedelta

from bson import ObjectId

from agenda.services.free_slots import (
    AGENDA_MINUTES, BUSY, CLOSED, NOT_ROUND, PAST, check_slot, describe_slot, next_free_slots,
)
from ai_agents.interfaces.ai_interface import IAI
from ai_agents.interfaces.tool_interface import ITool
from chat.interfaces.conversation_repository_interface import IConversationRepository
from crm.interfaces.customer_repository_interface import ICustomerRepository
from crm.models.custumer_model import Customer
from crm.services.business_hours import local_tz, to_local, to_utc_naive
from gateway.interfaces.chat_interface import IChat
from utils.logger import logger, to_json_dump

MEETING_AGENT = "meeting_agent"
WAITING, BOOKED, HANDED_OFF = "aguardando", "agendada", "equipe"

UNAVAILABLE = {
    BUSY: "Esse horário já está ocupado na nossa agenda. Teria algum outro horário que fique bom para você?",
    CLOSED: ("Nossas reuniões são de segunda a sexta, das 9h às 19h. "
             "Teria algum outro horário nesse intervalo que fique bom para você?"),
    NOT_ROUND: ("Nossas reuniões começam sempre em hora cheia ou meia hora (por exemplo, 14h ou 14h30). "
                "Qual horário fica melhor para você?"),
    PAST: ("Esse horário está muito em cima e não conseguimos preparar a reunião a tempo. "
           "Teria algum outro horário que fique bom para você?"),
}
QUESTIONS = {
    "horarios": "Sem problemas. Qual horário seria melhor para você?",
    "dia": "Sem problemas. Qual seria o melhor dia e horário para você?",
}


def _first_name(customer: Customer) -> str:
    first = (customer.name or "").strip().split(" ")[0]
    return "" if not first or first.startswith("WhatsApp") else first


def _parse_day(value: str | None, today: date) -> date | None:
    """'07/11/2026', '07/11' ou '2026-11-07' -> data. Sem ano: próxima ocorrência."""
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        day = datetime.strptime(f"{text}/{today.year}", "%d/%m/%Y").date()
    except ValueError:
        return None
    return day if day >= today else day.replace(year=today.year + 1)


def _parse_time(value: str | None) -> tuple[int, int] | None:
    """'14:30', '14h30', '14h', '14' -> (14, 30)."""
    text = (value or "").strip().lower().replace("h", ":").replace(".", ":")
    if not text:
        return None
    parts = [p for p in text.split(":") if p != ""]
    try:
        hour, minute = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return None
    return (hour, minute) if 0 <= hour <= 23 and 0 <= minute <= 59 else None


def _local_to_utc(day: date, hour: int, minute: int) -> datetime:
    return to_utc_naive(datetime(day.year, day.month, day.day, hour, minute, tzinfo=local_tz()))


def offered_slots(customer: Customer) -> list[datetime]:
    slots = []
    for value in (customer.meeting_offer or {}).get("slots") or []:
        try:
            slots.append(datetime.fromisoformat(value))
        except (TypeError, ValueError):
            continue
    return slots


def start_offer(customer_repository: ICustomerRepository, customer_id: str, slots: list[datetime],
                next_step: str) -> None:
    """Chamado por `oferecer_horarios`: a IA continua na conversa, agora com o agente de agendamento."""
    customer_repository.update(id=customer_id, attributes={
        "agent": MEETING_AGENT,
        "next_step": next_step[:160],
        "meeting_offer": {"slots": [s.isoformat() for s in slots], "round": 1, "status": WAITING,
                          "offered_at": datetime.utcnow().isoformat()},
    })


class _MeetingTool(ITool):
    model = "gpt-5.1"

    def __init__(
        self,
        ai_client: IAI,
        chat_client: IChat,
        customer_repository: ICustomerRepository,
        conversation_repository: IConversationRepository,
    ):
        self.ai = ai_client
        self.chat = chat_client
        self.customer = customer_repository
        self.conversation = conversation_repository

    # --- Estado -------------------------------------------------------------------------------

    @staticmethod
    def _load(customer: dict) -> Customer | None:
        try:
            return Customer.objects(id=ObjectId(customer.get("id"))).first()
        except Exception:
            return None

    def _save_offer(self, doc: Customer, **changes) -> None:
        offer = {**(doc.meeting_offer or {}), **changes}
        self.customer.update(id=str(doc.id), attributes={"meeting_offer": offer})
        doc.meeting_offer = offer

    @staticmethod
    def _say(text: str) -> list[dict]:
        return [{"role": "assistant", "content": text}]

    # --- Passar para a equipe -----------------------------------------------------------------

    def _pause_ai(self, doc: Customer, next_step: str, status: str) -> None:
        """A IA sai da conversa (como em `resumo`/`humano`): a equipe continua pelo painel."""
        self.customer.update(id=str(doc.id), attributes={
            "blocked_until": datetime.utcnow() + timedelta(hours=24),
            "customer_custom_tag": "operador humano",
            "new_service": True,
            "agent": "response_orchestrator",
            "next_step": next_step[:160],
            "meeting_offer": {**(doc.meeting_offer or {}), "status": status},
        })
        conversation = self.conversation.get_active_conversation(customer=str(doc.id))
        if conversation:
            conversation.tag = "operador humano"
            conversation.ai_active = False
            conversation.needs_attention = True
            self.conversation.update_conversation(conversation)

    def _hand_off(self, doc: Customer) -> list[dict]:
        logger.info("[MEETING TOOLS] Cliente %s não conseguiu marcar a reunião; vai para a equipe.", doc.phone)
        self._pause_ai(doc, "Combinar o horário da reunião com o cliente (a IA não conseguiu agendar)", HANDED_OFF)
        name = _first_name(doc)
        greeting = f"Sem problemas, {name}." if name else "Sem problemas."
        return self._say(f"{greeting} Vou pedir para alguém da nossa equipe falar com você para combinar "
                         f"o melhor dia e horário da reunião.")

    def _retry(self, doc: Customer, text: str, **changes) -> list[dict]:
        """A tentativa extra da IA. Já usada -> a conversa vai para a equipe."""
        if int((doc.meeting_offer or {}).get("round") or 1) >= 2:
            return self._hand_off(doc)
        self._save_offer(doc, round=2, **changes)
        return self._say(text)

    def _log(self, customer: dict, arguments: dict) -> None:
        logger.info("[MEETING TOOLS] %s para %s: %s", self.name, customer.get("phone"), to_json_dump(arguments))


class BookMeetingTool(_MeetingTool):
    """O cliente aceitou um horário oferecido ou disse um horário dele."""

    name = "agendar_reuniao"

    def _start(self, doc: Customer, arguments: dict, now: datetime) -> tuple[datetime | None, str | None]:
        """Início pedido (UTC) e o motivo se não der. Sem data: o dia dos horários oferecidos."""
        hour_minute = _parse_time(arguments.get("horario"))
        if not hour_minute:
            return None, None
        today = to_local(now).date()
        day = _parse_day(arguments.get("data"), today)
        days = [day] if day else list(dict.fromkeys(to_local(s).date() for s in offered_slots(doc))) or [today]
        first_problem = None
        for current in days:
            start = _local_to_utc(current, *hour_minute)
            problem = check_slot(start, now=now)
            if problem is None:
                return start, None
            first_problem = first_problem or (start, problem)
        return first_problem

    async def execute(self, function_call_id: str, call_id: str, call_name: str, customer: dict,
                      context: list, arguments: dict) -> list[dict]:
        from agenda.services.agenda_service import AgendaService, ScheduleConflict

        self._log(customer, arguments)
        doc = self._load(customer)
        if not doc:
            return []
        now = datetime.utcnow()
        start, problem = self._start(doc, arguments, now)
        if start is None:
            return self._say("Pode me confirmar o dia e o horário que ficam melhor para você?")
        if problem:
            return self._retry(doc, UNAVAILABLE[problem])

        try:
            AgendaService().schedule("reuniao_online", start, start + timedelta(minutes=AGENDA_MINUTES),
                                     customer_id=str(doc.id), notes="Agendada pela IA no WhatsApp.",
                                     notify_customer=True)
        except ScheduleConflict:
            return self._retry(doc, UNAVAILABLE[BUSY])
        except Exception:
            logger.exception("[MEETING TOOLS] Falha ao agendar a reunião de %s", doc.phone)
            return self._hand_off(doc)

        # A confirmação (dia, hora e link) sai pela agenda; a IA não manda outra mensagem.
        local = to_local(start)
        self._save_offer(doc, booked_start=start.isoformat())
        self._pause_ai(doc, f"Reunião agendada pela IA: {local:%d/%m às %H:%M}", BOOKED)
        return []


class OtherSlotsTool(_MeetingTool):
    """O cliente só pode num período ou num dia: dois horários livres dentro disso."""

    name = "oferecer_outros_horarios"

    async def execute(self, function_call_id: str, call_id: str, call_name: str, customer: dict,
                      context: list, arguments: dict) -> list[dict]:
        self._log(customer, arguments)
        doc = self._load(customer)
        if not doc:
            return []
        if int((doc.meeting_offer or {}).get("round") or 1) >= 2:
            return self._hand_off(doc)
        now = datetime.utcnow()
        period = (arguments.get("periodo") or "").strip().lower()
        day = _parse_day(arguments.get("data"), to_local(now).date())
        slots = next_free_slots(now=now, period=None if period in ("", "qualquer") else period, day=day,
                                exclude=offered_slots(doc))
        if not slots:
            return self._retry(doc, "Nesse período não tenho horário livre na agenda. "
                                    "Qual outro dia e horário seria melhor para você?", slots=[])
        options = " ou ".join(describe_slot(s, now) for s in slots)
        question = "Algum desses horários fica bom para você?" if len(slots) > 1 else "Fica bom para você?"
        return self._retry(doc, f"Sem problemas. Consigo {options}. {question}",
                           slots=[s.isoformat() for s in slots])


class AskTimeTool(_MeetingTool):
    """O cliente não pode e não disse outro horário: pergunta qual é melhor (uma vez só)."""

    name = "perguntar_horario"

    async def execute(self, function_call_id: str, call_id: str, call_name: str, customer: dict,
                      context: list, arguments: dict) -> list[dict]:
        self._log(customer, arguments)
        doc = self._load(customer)
        if not doc:
            return []
        reason = (arguments.get("motivo") or "").strip().lower()
        return self._retry(doc, QUESTIONS.get(reason, QUESTIONS["dia"]))
