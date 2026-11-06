"""IA de social e corporativo agenda a reunião com o time técnico (pedido do João, 06/11/2026).

Reuniões de segunda a sexta, das 8h às 19h. Depois de oferecer os horários, a IA marca o que o cliente aceitar (ou o horário
que ele disser, se estiver livre), oferece outros horários num período/dia ou pergunta o melhor horário
uma vez só; se ainda não der, passa para a equipe.
"""
import asyncio
from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time

from agenda.models import CalendarEvent
from agenda.services.free_slots import BUSY, CLOSED, NOT_ROUND, PAST, check_slot, next_free_slots
from ai_agents.agents.meeting_agent import MeetingAgent
from ai_agents.tools.meeting_booking_tools import AskTimeTool, BookMeetingTool, OtherSlotsTool
from chat.models.conversation_model import ConversationModel
from chat.repositories.conversation_repository import ConversationRepository
from crm import domain
from crm.models.custumer_model import Customer
from crm.repositories.customer_repository import CustomerRepository
from crm.services.business_hours import to_local
from database.client.mongodb_client import MongoDBClient

# Segunda 19/10/2026, 12:00 UTC = 9:00 em Brasília.
NOW = "2026-10-19 12:00:00"


def utc(day: int, hour: int, minute: int = 0) -> datetime:
    """Horário de Brasília (UTC-3) em 10/2026 -> UTC sem fuso."""
    return datetime(2026, 10, day, hour + 3, minute)


def busy(day: int, hour: int, minute: int = 0, minutes: int = 60):
    start = utc(day, hour, minute)
    CalendarEvent(type="reuniao_online", title="Outra reunião", start=start, end=start + timedelta(minutes=minutes),
                  status="confirmado").save()


def lead_waiting(slots: list[datetime], round_: int = 1, phone: str = "5562900002001") -> Customer:
    lead = Customer(name="Ana Paula", phone=phone, agent="meeting_agent",
                    meeting_offer={"slots": [s.isoformat() for s in slots], "round": round_, "status": "aguardando"})
    lead.save()
    ConversationRepository.create_conversation(lead)
    return lead


def run(tool_class, lead: Customer, **arguments) -> list[dict]:
    tool = tool_class(ai_client=None, chat_client=None, customer_repository=CustomerRepository(MongoDBClient()),
                      conversation_repository=ConversationRepository())
    return asyncio.run(tool.execute("fc1", "call1", tool.name, lead.to_dict(), [], arguments))


def text(output: list[dict]) -> str:
    return output[0]["content"] if output else ""


def conversation_of(lead: Customer) -> ConversationModel:
    return ConversationModel.objects(customer=lead.id).order_by("-id").first()


def meetings(lead: Customer):
    return list(CalendarEvent.objects(customer=lead.id, type="reuniao_online", status="confirmado"))


def assert_handed_off(lead: Customer, output: list[dict]):
    assert "Vou pedir para alguém da nossa equipe falar com você" in text(output)
    lead.reload()
    conversation = conversation_of(lead)
    assert conversation.ai_active is False and conversation.tag == "operador humano" and conversation.needs_attention
    assert lead.meeting_offer["status"] == "equipe" and lead.agent == "response_orchestrator"
    assert "a IA não conseguiu agendar" in lead.next_step
    assert meetings(lead) == []


# --- Horário de reuniões: 8h às 19h -----------------------------------------------------------

@pytest.mark.django_db
def test_check_slot_rules():
    now = utc(19, 9)
    assert check_slot(utc(19, 18), now=now) is None  # termina 19:00
    assert check_slot(utc(19, 8), now=utc(19, 7)) is None
    assert check_slot(utc(19, 18, 30), now=now) == CLOSED  # terminaria 19:30
    assert check_slot(utc(19, 7, 30), now=utc(19, 6)) == CLOSED
    assert check_slot(utc(24, 9), now=now) == CLOSED  # sábado
    assert check_slot(utc(25, 10), now=now) == CLOSED  # domingo
    assert check_slot(utc(19, 14, 15), now=now) == NOT_ROUND
    assert check_slot(utc(19, 9, 20), now=now) == PAST  # menos de 30 min
    busy(19, 15)
    assert check_slot(utc(19, 14), now=now) == BUSY  # termina 15:00, sem folga
    assert check_slot(utc(19, 16), now=now) == BUSY  # começa colado no fim (16:00)
    assert check_slot(utc(19, 13, 30), now=now) is None  # termina 14:30, 30 min antes
    assert check_slot(utc(19, 16, 30), now=now) is None


@pytest.mark.django_db
def test_free_slots_by_period_and_day():
    now = utc(19, 9)
    afternoon = next_free_slots(now=now, period="tarde")
    assert [to_local(s).strftime("%d %H:%M") for s in afternoon] == ["19 12:00", "19 14:00"]
    night = next_free_slots(now=now, period="noite")
    assert [to_local(s).strftime("%d %H:%M") for s in night] == ["19 18:00", "20 18:00"]
    morning_friday = next_free_slots(now=now, period="manha", day=utc(23, 0).date())
    assert [to_local(s).strftime("%d %H:%M") for s in morning_friday] == ["23 08:00", "23 10:00"]
    # Não repete o que já foi oferecido.
    again = next_free_slots(now=now, period="tarde", exclude=afternoon)
    assert not set(again) & set(afternoon)
    assert next_free_slots(now=now, day=utc(25, 0).date()) == []  # domingo


# --- Aceitou um horário oferecido -------------------------------------------------------------

@pytest.mark.django_db
@freeze_time(NOW)
def test_accepting_an_offered_slot_books_and_hands_over(zapi_outbox):
    lead = lead_waiting([utc(19, 10), utc(19, 14)])
    output = run(BookMeetingTool, lead, data="19/10/2026", horario="14:00")

    assert output == []  # a confirmação sai pela agenda, sem mensagem repetida da IA
    [event] = meetings(lead)
    assert event.start == utc(19, 14) and event.end == utc(19, 15)  # 1 h na agenda
    assert any("Sua reunião com a LM Eventos está confirmada para 19/10/2026 às 14:00" in m.get("message", "")
               for m in zapi_outbox)
    lead.reload()
    assert lead.customer_state_now == domain.MEETING_SCHEDULED and "reuniao_agendada" in lead.flags
    assert lead.meeting_offer["status"] == "agendada" and lead.meeting_offer["booked_start"] == utc(19, 14).isoformat()
    assert lead.next_step == "Reunião agendada pela IA: 19/10 às 14:00"
    conversation = conversation_of(lead)
    assert conversation.ai_active is False and conversation.tag == "operador humano"


@pytest.mark.django_db
@freeze_time(NOW)
def test_time_without_day_uses_the_offered_day():
    lead = lead_waiting([utc(20, 10), utc(20, 14)])
    assert run(BookMeetingTool, lead, data="", horario="16h30") == []
    assert meetings(lead)[0].start == utc(20, 16, 30)


@pytest.mark.django_db
@freeze_time(NOW)
def test_offered_slot_taken_meanwhile_counts_as_unavailable():
    lead = lead_waiting([utc(19, 10), utc(19, 14)])
    busy(19, 14)
    output = run(BookMeetingTool, lead, data="19/10/2026", horario="14:00")
    assert text(output) == "Esse horário já está ocupado na nossa agenda. Teria algum outro horário que fique bom para você?"
    lead.reload()
    assert lead.meeting_offer["round"] == 2 and conversation_of(lead).ai_active is True


# --- Cliente diz outro horário ----------------------------------------------------------------

@pytest.mark.django_db
@freeze_time(NOW)
def test_client_time_free_is_booked():
    lead = lead_waiting([utc(19, 10), utc(19, 14)])
    assert run(BookMeetingTool, lead, data="21/10/2026", horario="17:30") == []
    assert meetings(lead)[0].start == utc(21, 17, 30)


@pytest.mark.django_db
@freeze_time(NOW)
def test_client_time_busy_asks_once_then_team_takes_over():
    lead = lead_waiting([utc(19, 10), utc(19, 14)])
    busy(21, 15)
    first = run(BookMeetingTool, lead, data="21/10/2026", horario="15:00")
    assert "Teria algum outro horário" in text(first)
    lead.reload()
    assert lead.meeting_offer["round"] == 2 and meetings(lead) == []

    second = run(BookMeetingTool, lead, data="21/10/2026", horario="16:00")  # colado no fim (16:00)
    assert_handed_off(lead, second)


@pytest.mark.django_db
@freeze_time(NOW)
def test_second_try_with_free_time_is_booked():
    lead = lead_waiting([utc(19, 10), utc(19, 14)], round_=2)
    assert run(BookMeetingTool, lead, data="22/10/2026", horario="09:00") == []
    assert meetings(lead)[0].start == utc(22, 9)


@pytest.mark.django_db
@freeze_time(NOW)
def test_client_time_out_of_hours_explains_the_hours():
    lead = lead_waiting([utc(19, 10), utc(19, 14)])
    output = run(BookMeetingTool, lead, data="21/10/2026", horario="19:00")
    assert text(output).startswith("Nossas reuniões são de segunda a sexta, das 8h às 19h.")
    assert "sábado" not in text(output)


# --- Período, dia e pergunta extra ------------------------------------------------------------

@pytest.mark.django_db
@freeze_time(NOW)
def test_period_offers_new_slots_once():
    lead = lead_waiting([utc(19, 10), utc(19, 14)])
    output = run(OtherSlotsTool, lead, periodo="tarde", data="")
    assert text(output) == ("Sem problemas. Consigo hoje às 12h ou hoje às 14h30. "
                            "Algum desses horários fica bom para você?")
    lead.reload()
    assert lead.meeting_offer["round"] == 2
    assert lead.meeting_offer["slots"] == [utc(19, 12).isoformat(), utc(19, 14, 30).isoformat()]

    # Aceitou um dos novos: marca.
    assert run(BookMeetingTool, lead, data="19/10/2026", horario="14:30") == []
    assert meetings(lead)[0].start == utc(19, 14, 30)


@pytest.mark.django_db
@freeze_time(NOW)
def test_period_rejected_again_goes_to_team():
    lead = lead_waiting([utc(19, 10), utc(19, 14)])
    run(OtherSlotsTool, lead, periodo="noite", data="")
    lead.reload()
    assert_handed_off(lead, run(AskTimeTool, lead, motivo="horarios"))


@pytest.mark.django_db
@freeze_time(NOW)
def test_day_without_time_offers_slots_that_day():
    lead = lead_waiting([utc(19, 10), utc(19, 14)])
    output = run(OtherSlotsTool, lead, periodo="qualquer", data="23/10/2026")
    assert text(output) == ("Sem problemas. Consigo sexta-feira (23/10) às 8h ou sexta-feira (23/10) às 10h. "
                            "Algum desses horários fica bom para você?")


@pytest.mark.django_db
@freeze_time(NOW)
def test_no_slot_in_period_asks_for_day_and_time():
    lead = lead_waiting([utc(19, 10), utc(19, 14)])
    output = run(OtherSlotsTool, lead, periodo="manha", data="24/10/2026")  # sábado: sem reunião
    assert text(output) == ("Nesse período não tenho horário livre na agenda. "
                            "Qual outro dia e horário seria melhor para você?")
    lead.reload()
    assert lead.meeting_offer["round"] == 2


@pytest.mark.django_db
@freeze_time(NOW)
@pytest.mark.parametrize("motivo, question", [
    ("horarios", "Sem problemas. Qual horário seria melhor para você?"),
    ("dia", "Sem problemas. Qual seria o melhor dia e horário para você?"),
])
def test_ask_time_only_once(motivo, question):
    lead = lead_waiting([utc(19, 10), utc(19, 14)])
    assert text(run(AskTimeTool, lead, motivo=motivo)) == question
    lead.reload()
    assert lead.meeting_offer["round"] == 2 and conversation_of(lead).ai_active is True
    assert_handed_off(lead, run(AskTimeTool, lead, motivo=motivo))


# --- Agente -----------------------------------------------------------------------------------

class FakeAI:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def create_model_response(self, **kwargs):
        self.calls.append(kwargs)
        return {"output": self.output}


class FakeTools:
    def __init__(self):
        self.called = []

    def get(self, name):
        tools = self

        class Tool:
            async def execute(self, **kwargs):
                tools.called.append((name, kwargs["arguments"]))
                return [{"role": "assistant", "content": f"ok {name}"}]

        return Tool()


@pytest.mark.django_db
@freeze_time(NOW)
def test_agent_prompt_lists_offered_slots_and_calls_one_tool():
    lead = lead_waiting([utc(19, 10), utc(20, 14)])
    calls = [
        {"type": "function_call", "status": "completed", "name": "agendar_reuniao", "id": "1", "call_id": "c1",
         "arguments": '{"data": "20/10/2026", "horario": "14:00"}'},
        {"type": "function_call", "status": "completed", "name": "perguntar_horario", "id": "2", "call_id": "c2",
         "arguments": '{"motivo": "dia"}'},
    ]
    ai, tools = FakeAI(calls), FakeTools()
    agent = MeetingAgent(agent_container=None, tool_container=tools, message_repository=None, ai_client=ai)
    output = asyncio.run(agent.execute([{"role": "user", "content": "amanhã às 14h"}], lead.to_dict()))

    assert output == [{"role": "assistant", "content": "ok agendar_reuniao"}]
    assert tools.called == [("agendar_reuniao", {"data": "20/10/2026", "horario": "14:00"})]
    prompt = ai.calls[0]["input"][0]["content"]
    assert "- 19/10/2026 10:00 (hoje às 10h)" in prompt and "- 20/10/2026 14:00 (amanhã às 14h)" in prompt
    assert "segunda-feira, 19/10/2026 09:00" in prompt and "- sexta-feira: 23/10/2026" in prompt
    assert "Nome do cliente: Ana" in prompt


@pytest.mark.django_db
@freeze_time(NOW)
def test_agent_plain_answer_goes_to_client():
    lead = lead_waiting([utc(19, 10), utc(20, 14)])
    ai = FakeAI([{"type": "message", "content": [{"type": "output_text", "text": "Qual dos dois horários você prefere?"}]}])
    agent = MeetingAgent(agent_container=None, tool_container=FakeTools(), message_repository=None, ai_client=ai)
    output = asyncio.run(agent.execute([{"role": "user", "content": "pode ser"}], lead.to_dict()))
    assert output == [{"role": "assistant", "content": "Qual dos dois horários você prefere?"}]


# --- Follow-up --------------------------------------------------------------------------------

@pytest.mark.django_db
def test_follow_up_skips_client_choosing_the_meeting_time():
    old = datetime.now() - timedelta(hours=5)
    Customer(name="Escolhendo", phone="5562900002101", agent="meeting_agent", last_message_attendant=old).save()
    Customer(name="Parado", phone="5562900002102", agent="event_agent", last_message_attendant=old).save()
    names = [c["name"] for c in CustomerRepository(MongoDBClient()).get_customers_needing_follow_up()]
    assert names == ["Parado"]
