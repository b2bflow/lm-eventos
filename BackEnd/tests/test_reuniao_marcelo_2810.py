"""Reunião com o Marcelo (28/10): funil só com os qualificados pela IA, etapa "Reunião agendada",
dois horários oferecidos pela IA no social e no corporativo e aviso no grupo de atendimento."""
import asyncio
from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time

from agenda.models import CalendarEvent
from agenda.services.agenda_service import AgendaService
from agenda.services.free_slots import describe_slot, next_free_slots
from ai_agents.tools.meeting_slots_tool import MeetingSlotsTool, build_meeting_message
from chat.models.conversation_model import ConversationModel
from chat.repositories.conversation_repository import ConversationRepository
from crm import domain
from crm.models.custumer_model import Customer
from crm.models.lm_settings_model import LmSettings
from crm.models.quote_model import Quote
from crm.repositories.customer_repository import CustomerRepository
from crm.services import funnel_entry
from crm.services.notification_service import NotificationService, ai_lead_text
from crm.services.quote_service import QuoteService
from database.client.mongodb_client import MongoDBClient

FUNNEL = "/api/v1/crm/funnel/"


@pytest.fixture
def group_notices(monkeypatch):
    """O aviso do grupo roda em thread; nos testes, só registra quem seria avisado."""
    notified = []
    monkeypatch.setattr(funnel_entry, "_notify_group", notified.append)
    return notified


def ai_qualify(customer: Customer):
    quote = Quote(customer=customer, status="ANALYSIS").save()
    QuoteService().update_quote(str(quote.id), {"status": "WAITING_BUDGET", "guest_count": 120})
    customer.reload()


@pytest.mark.django_db
def test_ai_qualified_lead_shows_in_qualified_column(api_client, group_notices):
    lead = Customer(name="João Pedro", phone="5562900001001").save()
    ai_qualify(lead)

    # Antes ficava WAITING_BUDGET, que nenhuma coluna mostrava
    assert lead.customer_state_now == domain.QUALIFIED
    board = api_client.get(FUNNEL).data
    assert [c["id"] for c in board[domain.QUALIFIED]["results"]] == [str(lead.id)]
    assert group_notices == [str(lead.id)]

    # Qualificar de novo não avisa o grupo de novo
    ai_qualify(lead)
    assert group_notices == [str(lead.id)]


@pytest.mark.django_db
def test_legacy_waiting_budget_card_appears_as_qualified(api_client):
    lead = Customer(name="Antigo", phone="5562900001002", customer_state_now="WAITING_BUDGET",
                    funnel_entered_at=datetime.utcnow()).save()
    board = api_client.get(FUNNEL).data
    assert [c["id"] for c in board[domain.QUALIFIED]["results"]] == [str(lead.id)]


@pytest.mark.django_db
def test_ai_qualification_does_not_move_lead_back(group_notices):
    lead = Customer(name="Adiante", phone="5562900001003", customer_state_now=domain.PROPOSAL_SENT,
                    funnel_entered_at=datetime.utcnow()).save()
    ai_qualify(lead)
    assert lead.customer_state_now == domain.PROPOSAL_SENT


@pytest.mark.django_db
def test_board_has_meeting_column_between_qualified_and_proposal(api_client):
    board = api_client.get(FUNNEL).data
    keys = list(board)
    assert keys.index(domain.QUALIFIED) + 1 == keys.index(domain.MEETING_SCHEDULED)
    assert keys.index(domain.MEETING_SCHEDULED) + 1 == keys.index(domain.PROPOSAL_SENT)
    assert board[domain.MEETING_SCHEDULED]["label"] == "Reunião agendada"


@pytest.mark.django_db
@freeze_time("2026-10-19 12:00:00")
def test_scheduling_a_meeting_moves_card_to_meeting_stage():
    lead = Customer(name="Ana", phone="5562900001004", customer_state_now=domain.QUALIFIED,
                    funnel_entered_at=datetime.utcnow()).save()
    start = datetime(2026, 10, 20, 15, 0)
    AgendaService().schedule("reuniao_online", start, start + timedelta(minutes=40), customer_id=str(lead.id),
                             notify_customer=False)
    lead.reload()
    assert lead.customer_state_now == domain.MEETING_SCHEDULED

    # Lead mais adiante não volta
    later = Customer(name="Bia", phone="5562900001005", customer_state_now=domain.PROPOSAL_SENT,
                     funnel_entered_at=datetime.utcnow()).save()
    AgendaService().schedule("reuniao_online", start + timedelta(hours=2), start + timedelta(hours=2, minutes=40),
                             customer_id=str(later.id), notify_customer=False)
    later.reload()
    assert later.customer_state_now == domain.PROPOSAL_SENT


@pytest.mark.django_db
def test_meeting_stage_transitions(api_client):
    lead = Customer(name="Cris", phone="5562900001006", customer_state_now=domain.QUALIFIED,
                    funnel_entered_at=datetime.utcnow()).save()
    url = f"/api/v1/crm/customers/{lead.id}/stage/"
    assert api_client.post(url, {"stage": domain.MEETING_SCHEDULED}, format="json").status_code == 200
    assert api_client.post(url, {"stage": domain.QUALIFIED}, format="json").status_code == 200


# --- Horários livres -----------------------------------------------------------------------

@pytest.mark.django_db
def test_free_slots_respect_business_hours_conflicts_and_gap():
    # Segunda 19/10/2026, 12:00 UTC = 9:00 em Brasília. Primeiro candidato: 10:00.
    now = datetime(2026, 10, 19, 12, 0)
    CalendarEvent(type="bloqueio", title="Almoço", start=datetime(2026, 10, 19, 13, 0),
                  end=datetime(2026, 10, 19, 14, 0), status="confirmado").save()
    slots = next_free_slots(now=now)
    # Bloqueio 10:00-11:00 Brasília: 10:00, 10:30 e 11:00 (sem 30 min de folga) caem fora. Livre: 11:30.
    assert slots[0] == datetime(2026, 10, 19, 14, 30)
    assert slots[1] - slots[0] >= timedelta(hours=2)
    assert describe_slot(slots[0], now) == "hoje às 11h30"
    assert describe_slot(slots[1], now) == "hoje às 13h30"


def _meeting(day: int, hour: int, minute: int = 0, minutes: int = 60):
    """Reunião já marcada, horário de Brasília (UTC-3) em 10/2026."""
    start = datetime(2026, 10, day, hour + 3, minute)
    CalendarEvent(type="reuniao_online", title="Reunião", start=start, end=start + timedelta(minutes=minutes),
                  status="confirmado").save()


@pytest.mark.django_db
def test_free_slots_keep_30_min_from_existing_meetings():
    # Segunda 19/10 às 9:00. Reuniões às 12:00-13:00 e 16:00-17:00 (1 h na agenda).
    _meeting(19, 12)
    _meeting(19, 16)
    offered = set()
    for minutes_after in range(0, 8 * 60, 30):
        now = datetime(2026, 10, 19, 11, 0) + timedelta(minutes=minutes_after)
        offered.update(describe_slot(s, datetime(2026, 10, 19, 12, 0)) for s in next_free_slots(count=2, now=now))
    # Oferta ocupa 1 h: 11:00 termina 12:00 (sem folga) e 13:00 começa colado no fim: não podem.
    for blocked in ("hoje às 11h", "hoje às 11h30", "hoje às 12h", "hoje às 12h30", "hoje às 13h",
                    "hoje às 15h", "hoje às 15h30", "hoje às 16h", "hoje às 16h30", "hoje às 17h"):
        assert blocked not in offered
    assert "hoje às 10h30" in offered  # ocupa até 11:30, 30 min antes
    assert "hoje às 13h30" in offered  # 30 min depois do fim (13:00)
    assert "hoje às 17h30" in offered  # 30 min depois do fim (17:00)


@pytest.mark.django_db
def test_free_slots_buffer_exactly_30_min_is_allowed_and_only_round_times():
    # Reunião 9:00-10:00: 10:30 fica a exatamente 30 min do fim e pode.
    _meeting(19, 9, minutes=60)
    now = datetime(2026, 10, 19, 10, 0)  # 7:00 Brasília
    slots = next_free_slots(now=now)
    assert describe_slot(slots[0], now) == "hoje às 10h30"
    for s in next_free_slots(count=2, now=now) + next_free_slots(now=datetime(2026, 10, 19, 12, 7)):
        assert s.minute in (0, 30)


@pytest.mark.django_db
def test_free_slots_reserve_one_hour_and_end_by_19h():
    # Sexta 23/10 às 15:00 Brasília: ocupando 1 h, o último horário do dia é 18:00 (termina 19:00).
    now = datetime(2026, 10, 23, 18, 0)
    slots = next_free_slots(now=now)
    assert [describe_slot(s, now) for s in slots] == ["hoje às 16h", "hoje às 18h"]
    # Sexta 17:30: não cabe mais nada hoje e não tem reunião no fim de semana: vai para segunda.
    now = datetime(2026, 10, 23, 20, 30)
    assert [describe_slot(s, now) for s in next_free_slots(now=now)] == [
        "segunda-feira (26/10) às 9h", "segunda-feira (26/10) às 11h"]


@pytest.mark.django_db
def test_free_slots_skip_to_next_business_day():
    # Sábado 24/10 às 11:30 Brasília: fim de semana não tem reunião, vai para segunda.
    now = datetime(2026, 10, 24, 14, 30)
    slots = next_free_slots(now=now)
    assert describe_slot(slots[0], now) == "segunda-feira (26/10) às 9h"
    assert describe_slot(slots[1], now) == "segunda-feira (26/10) às 11h"


def test_meeting_message_has_two_options():
    now = datetime(2026, 10, 19, 12, 0)
    slots = [datetime(2026, 10, 19, 18, 0), datetime(2026, 10, 20, 13, 0)]
    text = build_meeting_message("Ana Paula", "Casamento", slots, now)
    assert text.startswith("Perfeito, Ana. Estamos analisando o seu pedido")
    assert "reunião de 40 minutos entre você e o nosso time técnico" in text
    assert "todos os detalhes do seu casamento" in text
    assert text.endswith("Se nos organizarmos para falar hoje às 15h ou amanhã às 10h, você consegue?")
    assert build_meeting_message(None, "corporativo", [], now).endswith("Qual o melhor dia e horário para você?")


# --- Ferramenta da IA -----------------------------------------------------------------------

@pytest.mark.django_db
@freeze_time("2026-10-19 12:00:00")
def test_meeting_tool_keeps_ai_qualifies_lead_and_offers_slots(group_notices):
    lead = Customer(name="Marina", phone="5562900001007", agent="event_agent").save()
    conversation = ConversationRepository.create_conversation(lead)
    tool = MeetingSlotsTool(ai_client=None, chat_client=None,
                            customer_repository=CustomerRepository(MongoDBClient()),
                            conversation_repository=ConversationRepository())
    arguments = {"data_evento": "12/12/2026", "numero_pessoas": "120", "tipo_evento": "Casamento",
                 "local_evento": "Espaço Jardim", "espaco": "aberto", "horario_evento": "19h",
                 "dj_ou_banda": "DJ", "recursos_adicionais": ""}
    output = asyncio.run(tool.execute("fc1", "call1", "oferecer_horarios", lead.to_dict(), [], arguments))

    assert output == [{"role": "assistant", "content": output[0]["content"]}]
    assert "hoje às 10h ou hoje às 12h" in output[0]["content"]
    lead.reload()
    conversation = ConversationModel.objects(id=conversation.id).first()
    # A IA continua: a resposta do cliente vai para o agente de agendamento (06/11).
    assert conversation.ai_active is True and conversation.tag == "AGENTE"
    assert lead.agent == "meeting_agent" and lead.blocked_until is None
    assert lead.meeting_offer["round"] == 1 and len(lead.meeting_offer["slots"]) == 2
    assert lead.ai_qualified_at is not None and lead.customer_state_now == domain.QUALIFIED
    assert lead.funnel_entered_at is not None and lead.guest_count == 120
    assert "hoje às 10h ou hoje às 12h" in lead.next_step
    assert group_notices == [str(lead.id)]


def _meeting_tool():
    return MeetingSlotsTool(ai_client=None, chat_client=None,
                            customer_repository=CustomerRepository(MongoDBClient()),
                            conversation_repository=ConversationRepository())


@pytest.mark.django_db
@freeze_time("2026-11-05 16:00:00")
def test_meeting_tool_handles_unknown_time_and_date_without_year(group_notices):
    # Log de produção 05/11: horario_evento "Não sei" derrubava update_quote e o cliente ficava sem resposta.
    lead = Customer(name="João", phone="5562900001008", agent="event_agent").save()
    ConversationRepository.create_conversation(lead)
    arguments = {"data_evento": "10/01", "numero_pessoas": "100", "tipo_evento": "Aniversário de 15 anos",
                 "local_evento": "Casa de eventos zzz", "espaco": "Não sei", "horario_evento": "Não sei",
                 "dj_ou_banda": "DJ", "recursos_adicionais": "pista de dança com DJ"}
    output = asyncio.run(_meeting_tool().execute("fc1", "call1", "oferecer_horarios", lead.to_dict(), [], arguments))

    assert "reunião de 40 minutos" in output[0]["content"]
    lead.reload()
    assert lead.customer_state_now == domain.QUALIFIED and lead.guest_count == 100
    assert lead.event_date == datetime(2027, 1, 10)  # sem ano: próxima ocorrência
    quote = Quote.objects(customer=lead).first()
    assert not quote.event_time
    assert "Horario evento: Não sei" in quote.notes


@pytest.mark.parametrize("raw, expected", [
    ("19h", "19h00"), ("20:30", "20h30"), ("a partir das 21h", "21h00"),
    ("Não sei", None), ("à noite", None), ("", None),
])
def test_tool_event_time_never_raises(raw, expected):
    assert _meeting_tool()._get_event_time({"horario_evento": raw}) == expected


@pytest.mark.django_db
@freeze_time("2026-10-19 12:00:00")
def test_meeting_tool_still_answers_when_quote_update_fails(group_notices, monkeypatch):
    lead = Customer(name="Lia", phone="5562900001009", agent="event_agent").save()
    ConversationRepository.create_conversation(lead)

    def boom(*args, **kwargs):
        raise RuntimeError("falha qualquer")

    monkeypatch.setattr(QuoteService, "update_quote", boom)
    arguments = {"data_evento": "12/12/2026", "numero_pessoas": "80", "tipo_evento": "Casamento",
                 "local_evento": "Espaço", "espaco": "aberto", "horario_evento": "19h",
                 "dj_ou_banda": "DJ", "recursos_adicionais": ""}
    output = asyncio.run(_meeting_tool().execute("fc1", "call1", "oferecer_horarios", lead.to_dict(), [], arguments))
    assert "hoje às 10h ou hoje às 12h" in output[0]["content"]


# --- Grupo de atendimento -------------------------------------------------------------------

@pytest.mark.django_db
def test_group_notice_goes_to_configured_group(zapi_outbox):
    settings = LmSettings.get()
    settings.ai_leads_group = "120363019502650977-group"
    settings.save()
    lead = Customer(name="Lia", phone="5562999990001", celebration_type="Casamento", guest_count=150,
                    next_step="Confirmar a reunião").save()
    assert NotificationService().notify_ai_lead(lead)
    sent = zapi_outbox[-1]
    assert sent["phone"] == "120363019502650977-group"
    assert sent["message"].splitlines()[0] == "Novo lead qualificado pela IA"
    assert "Telefone: (62) 99999-0001" in ai_lead_text(lead)


def test_zapi_accepts_group_ids():
    from gateway.adapters.zapi_adapter import ZAPIClient
    client = ZAPIClient()
    assert client.is_group("120363019502650977-group")
    assert not client.is_group("5562999990001")
    assert client._resolve_phone("120363019502650977-group") == "120363019502650977-group"


@pytest.mark.django_db
def test_groups_endpoint_is_admin_only(api_client, sdr_api, monkeypatch):
    from gateway.adapters.zapi_adapter import ZAPIClient
    monkeypatch.setattr(ZAPIClient, "list_groups", lambda self: [{"id": "1-group", "name": "GT LM Atendimento"}])
    assert api_client.get("/api/v1/crm/settings/whatsapp-groups/").data == [{"id": "1-group", "name": "GT LM Atendimento"}]
    assert sdr_api.get("/api/v1/crm/settings/whatsapp-groups/").status_code == 403


# --- Conjuntos de som: preço do conjunto, peças no estoque e no PDF ---------------------------

def _table():
    from sales.catalog import merge_price_table
    return merge_price_table(None)


def test_sound_tier_carries_its_pieces_and_checks_stock_by_piece():
    from sales.services.quote_calculator import CorporateInput, calculate_corporativo
    result = calculate_corporativo(CorporateInput(guests=100), _table(), availability={"som_caixa_ativa": 3})
    line = next(l for l in result.lines if l["code"] == "som_ate_150")
    assert line["subtotal"] == 1300 and [(c["name"], c["qty"]) for c in line["components"]] == [
        ("Caixa de som ativa", 4), ("Microfone sem fio", 1)]
    assert any("Caixa de som ativa: pedido 4, disponível 3" in (r["detail"] or "") for r in result.lock_reasons)


def test_ceremony_sound_pieces_are_chosen_in_the_calculator():
    from sales.services.quote_calculator import SocialInput, calculate_social
    default = calculate_social(SocialInput(guests=100, ceremony_sound=True), _table())
    ceremony = next(l for l in default.lines if l["code"] == "som_cerimonia")
    assert [c["code"] for c in ceremony["components"]] == ["som_caixa_ativa", "som_pedestal", "som_mesa_digital",
                                                           "som_mic_sem_fio"]
    custom = calculate_social(SocialInput(guests=100, ceremony_sound=True,
                                          ceremony_items={"som_caixa_ativa": 2, "som_mic_sem_fio": 1}), _table())
    ceremony = next(l for l in custom.lines if l["code"] == "som_cerimonia")
    assert [(c["code"], c["qty"]) for c in ceremony["components"]] == [("som_caixa_ativa", 2), ("som_mic_sem_fio", 1)]
    with pytest.raises(ValueError, match="fora do conjunto"):
        calculate_social(SocialInput(guests=100, ceremony_sound=True, ceremony_items={"luz_par_led": 1}), _table())


def test_pdf_shows_pieces_never_the_set_name():
    from sales.services.proposal_pdf import build_pdf_context
    from sales.services.quote_calculator import SocialInput, calculate_social
    result = calculate_social(SocialInput(guests=100, ceremony_sound=True, dance_floor=False), _table()).to_dict()
    proposal = {"mode": "social", "inputs": {}, "lines": result["lines"], "costs": result["operational"],
                "items_total": result["items_total"], "total": result["total"]}
    settings = {"proposal_validity_days": 5, "payment_terms_text": "", "down_payment_text": "", "cancellation_text": ""}
    items = [i for b in build_pdf_context(proposal, {"name": "Ana"}, settings)["blocks"] for i in b["items"]]
    text = " | ".join(items)
    assert "Som de cerimônia" not in text and "Som até 150" not in text
    # Caixas do som até 150 e do som de cerimônia somam
    assert "08 Caixa de som ativa" in items and "02 Pedestal de microfone" in items
    assert "02 Microfone sem fio" in items and "01 Mesa de canais digital" in items


@pytest.mark.django_db
def test_accepting_reserves_the_pieces_of_the_set():
    from inventory.models import InventoryItem, InventoryReservation
    from inventory.services.inventory_service import InventoryService
    box = InventoryItem(code="som_caixa_ativa", line="Som", name="Caixa de som ativa", qty_total=10).save()
    lines = [{"code": "som_ate_150", "qty": 1, "components": [{"code": "som_caixa_ativa", "qty": 4},
                                                              {"code": "som_mic_sem_fio", "qty": 1}]}]
    InventoryService().reserve("p1", None, lines, datetime(2026, 11, 1), datetime(2026, 11, 2))
    assert [(r.item.code, r.qty) for r in InventoryReservation.objects(proposal_id="p1")] == [(box.code, 4.0)]


@pytest.mark.django_db
def test_values_tab_lists_ceremony_set_with_its_pieces():
    from sales.services.pricing_service import price_settings, update_price_settings
    tiers = {t["code"]: t for t in price_settings()["sound_tiers"]}
    assert tiers["som_ate_150"]["components"] == "4 Caixa de som ativa, 1 Microfone sem fio"
    assert "som_cerimonia" in tiers
    update_price_settings({"sound_tiers": {"som_cerimonia": 1500}})
    assert {t["code"]: t for t in price_settings()["sound_tiers"]}["som_cerimonia"]["price"] == 1500
