"""Fila da SDR (P1): follow-up D+1, D+3, D+5 depois da proposta, perda automática em D+7 sem
resposta com reativação em 30 dias, e tarefa de reunião amanhã."""
from datetime import date, datetime, timedelta

import pytest

from agenda.models import CalendarEvent
from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from crm.container import CrmContainer
from crm.models.custumer_model import Customer
from crm.models.lm_settings_model import DEFAULT_BUSINESS_HOURS
from crm.models.sdr_task_model import SdrTask
from crm.services.business_hours import business_slot

# Segunda 19/10/2026, 10h em Brasília (13h UTC). Horários abaixo em UTC; 9h de Brasília = 12h UTC.
SENT_AT = datetime(2026, 10, 19, 13, 0)


def at(day: int, hour_utc: int = 3) -> datetime:
    """Momento do beat em outubro/novembro de 2026 (3h UTC = meia-noite em Brasília)."""
    return datetime(2026, 10, 1, hour_utc) + timedelta(days=day - 1)


@pytest.fixture
def service():
    return CrmContainer.get_sdr_task_service()


@pytest.fixture
def sent_lead():
    customer = Customer(name="Paula", phone="5562988887777", customer_state_now="PROPOSAL_SENT",
                        proposal_sent_at=SENT_AT, product="corporativo").save()
    ConversationModel(customer=customer, tag="AGENTE").save()
    return customer


def pending(customer, task_type=None):
    queryset = SdrTask.objects(customer=customer.id, status="pending")
    return queryset.filter(type=task_type) if task_type else queryset


def test_business_slot_skips_closed_days():
    # Domingo 25/10 -> segunda 26/10 às 9h
    assert business_slot(DEFAULT_BUSINESS_HOURS, date(2026, 10, 25), "09:00") == datetime(2026, 10, 26, 12, 0)
    # Sábado abre 8h-12h: 9h vale
    assert business_slot(DEFAULT_BUSINESS_HOURS, date(2026, 10, 24), "09:00") == datetime(2026, 10, 24, 12, 0)


@pytest.mark.django_db
def test_follow_ups_d1_d3_d5_created_on_their_day_once(service, sent_lead):
    assert service.run_proposal_cadence(now=at(19, 20)) == {"follow_ups": 0, "lost": 0}

    service.run_proposal_cadence(now=at(20))
    d1 = pending(sent_lead, "follow_up_d1").get()
    assert d1.due_at == datetime(2026, 10, 20, 12, 0)
    assert service.run_proposal_cadence(now=at(20, 15))["follow_ups"] == 0

    service.run_proposal_cadence(now=at(22))
    assert pending(sent_lead, "follow_up_d3").get().due_at == datetime(2026, 10, 22, 12, 0)
    # D+1 que ficou pendente sai da fila quando o D+3 entra
    assert pending(sent_lead, "follow_up_d1").count() == 0

    service.run_proposal_cadence(now=at(24))
    assert pending(sent_lead, "follow_up_d5").get().due_at == datetime(2026, 10, 24, 12, 0)
    assert SdrTask.objects(customer=sent_lead.id, type__startswith="follow_up").count() == 3


@pytest.mark.django_db
def test_beat_stopped_creates_only_latest_step(service, sent_lead):
    service.run_proposal_cadence(now=at(23))
    types = [t.type for t in SdrTask.objects(customer=sent_lead.id)]
    assert types == ["follow_up_d3"]


@pytest.mark.django_db
def test_d7_without_response_moves_to_lost_and_schedules_reactivation(service, sent_lead):
    service.run_proposal_cadence(now=at(20))
    result = service.run_proposal_cadence(now=at(26))
    assert result["lost"] == 1

    sent_lead.reload()
    assert sent_lead.customer_state_now == "LOST"
    assert sent_lead.lost_reason == "sem_resposta"
    reactivation = pending(sent_lead).get()
    assert reactivation.type == "reativar_lead"
    # 26/10 + 30 dias = quarta 25/11, às 9h
    assert reactivation.due_at == datetime(2026, 11, 25, 12, 0)
    assert SdrTask.objects(customer=sent_lead.id, type="follow_up_d1").get().status == "canceled"
    # Não perde de novo nem duplica a reativação
    assert service.run_proposal_cadence(now=at(27)) == {"follow_ups": 0, "lost": 0}


@pytest.mark.django_db
def test_d7_with_customer_reply_stays_in_proposal_sent(service, sent_lead):
    conversation = ConversationModel.objects.get(customer=sent_lead)
    MessageModel(conversation=conversation, customer=sent_lead, role="user", direction="INCOMING",
                 content="Vou analisar com o financeiro.", created_at=SENT_AT + timedelta(days=2)).save()
    assert service.run_proposal_cadence(now=at(26))["lost"] == 0
    sent_lead.reload()
    assert sent_lead.customer_state_now == "PROPOSAL_SENT"


@pytest.mark.django_db
def test_d7_with_answered_call_stays_in_proposal_sent(api_client, service, sent_lead):
    # A ligação é registrada com a hora real; a proposta foi enviada uma hora antes.
    sent_lead.update(proposal_sent_at=datetime.utcnow() - timedelta(hours=1))
    api_client.post(f"/api/v1/crm/customers/{sent_lead.id}/calls/", {"outcome": "atendeu"}, format="json")
    assert service.run_proposal_cadence(now=datetime.utcnow() + timedelta(days=10))["lost"] == 0


@pytest.mark.django_db
def test_human_operator_never_gets_cadence(service):
    partner = Customer(name="Parceiro", phone="5562977776666", customer_state_now="PROPOSAL_SENT",
                       proposal_sent_at=SENT_AT, human_operator=True).save()
    service.run_proposal_cadence(now=at(20))
    assert SdrTask.objects(customer=partner.id).count() == 0


@pytest.mark.django_db
def test_leaving_proposal_sent_cancels_cadence(api_client, service, sent_lead):
    service.run_proposal_cadence(now=at(20))
    resp = api_client.post(f"/api/v1/crm/customers/{sent_lead.id}/stage/", {"stage": "QUALIFIED"}, format="json")
    assert resp.status_code == 200, resp.data
    assert pending(sent_lead).count() == 0


@pytest.mark.django_db
def test_meeting_tomorrow_task_once_per_event(service, sent_lead):
    now = datetime(2026, 10, 20, 13, 0)  # terça 10h
    tomorrow = CalendarEvent(type="reuniao_online", title="Reunião", customer=sent_lead,
                             start=datetime(2026, 10, 21, 17, 0), end=datetime(2026, 10, 21, 18, 0)).save()
    CalendarEvent(type="visita_tecnica", title="Visita", customer=sent_lead, location="Rua 1",
                  start=datetime(2026, 10, 23, 17, 0), end=datetime(2026, 10, 23, 18, 0)).save()
    CalendarEvent(type="evento_confirmado", title="Evento", customer=sent_lead,
                  start=datetime(2026, 10, 21, 20, 0), end=datetime(2026, 10, 21, 23, 0)).save()

    assert service.create_meeting_tasks(now=now) == 1
    task = pending(sent_lead, "reuniao_amanha").get()
    assert task.metadata["event_id"] == str(tomorrow.id)
    assert task.due_at == now  # dentro do horário comercial: para agora
    assert service.create_meeting_tasks(now=now + timedelta(hours=2)) == 0


@pytest.mark.django_db
def test_queue_endpoint_lists_by_due_date(api_client, service, sent_lead):
    service.run_proposal_cadence(now=at(20))
    service.create_task(str(sent_lead.id), "ligar_15min", due_at=datetime(2026, 10, 19, 14, 0))
    data = api_client.get("/api/v1/crm/tasks/").data
    assert [t["type"] for t in data] == ["ligar_15min", "follow_up_d1"]
