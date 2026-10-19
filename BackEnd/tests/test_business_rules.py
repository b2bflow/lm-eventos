"""Furos de regra de negócio do processo com SDR: aceite e estoque, cálculo, qualificação,
agenda da Erica e escrita dos avisos automáticos."""
import re
from datetime import datetime
from io import StringIO

import pytest
from django.core.management import call_command
from freezegun import freeze_time

from agenda.models import CalendarEvent
from crm import domain
from crm.models.custumer_model import Customer
from crm.models.lm_settings_model import DEFAULT_QUICK_REPLIES, LmSettings
from crm.models.log_service_model import ServiceLog
from crm.models.sdr_task_model import SdrTask
from inventory.models import InventoryReservation
from sales.models import Proposal

PORTA = {"pickup_date": "2026-10-23", "return_date": "2026-10-26",
         "items": [{"code": "q30_torre_5m", "qty": 100}, {"code": "q30_cubo_5_faces", "qty": 8}]}
EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿⬀-⯿️]")


@pytest.fixture(autouse=True)
def frozen_now():
    with freeze_time("2026-10-19 13:00:00"):  # segunda, 10h em Brasília
        yield


@pytest.fixture
def stock():
    call_command("seed_inventory", stdout=StringIO())


@pytest.fixture
def contacts():
    cfg = LmSettings.get()
    cfg.approval_phone = "120363000000000000-group"
    cfg.erica_phone = "5562900000002"
    cfg.lucia_phone = "5562900000003"
    cfg.sdr_phone = "5562900000001"
    cfg.save()


def porta_lead(phone="5562988887777", name="Lucas"):
    return Customer(name=name, phone=phone, customer_state_now=domain.QUALIFIED, product="estrutura_porta").save()


def sent_proposal(client, lead, inputs=PORTA):
    proposal = client.post("/api/v1/sales/proposals/", {"customer_id": str(lead.id), "mode": "porta", "inputs": inputs},
                           format="json")
    assert proposal.status_code == 201, proposal.data
    sent = client.post(f"/api/v1/sales/proposals/{proposal.data['id']}/send/")
    assert sent.status_code == 200, sent.data
    return sent.data


def stage(client, lead, target, **extra):
    return client.post(f"/api/v1/crm/customers/{lead.id}/stage/", {"stage": target, **extra}, format="json")


# --- Aceite pelo card e estoque ------------------------------------------------------------

@pytest.mark.django_db
def test_dragging_to_accepted_without_a_sent_proposal_is_refused(sdr_api):
    lead = Customer(name="Ana", phone="5562911112222", customer_state_now=domain.PROPOSAL_SENT,
                    proposal_sent_at=datetime(2026, 10, 18), product="corporativo").save()
    resp = stage(sdr_api, lead, domain.PROPOSAL_ACCEPTED)
    assert resp.status_code == 400 and "proposta enviada" in resp.data["detail"]
    lead.reload()
    assert lead.customer_state_now == domain.PROPOSAL_SENT


@pytest.mark.django_db
def test_dragging_to_accepted_accepts_the_proposal_reserves_stock_and_tells_lucia(sdr_api, stock, contacts, zapi_outbox):
    lead = porta_lead()
    proposal = sent_proposal(sdr_api, lead)
    resp = stage(sdr_api, lead, domain.PROPOSAL_ACCEPTED)
    assert resp.status_code == 200, resp.data
    assert resp.data["customer_state_now"] == domain.PROPOSAL_ACCEPTED and resp.data["owner"] == "lucia"
    assert Proposal.objects.get(id=proposal["id"]).status == "aceita"
    assert InventoryReservation.objects(proposal_id=proposal["id"], status="reservado").count() == 2
    assert any(m.get("phone") == "5562900000003" and "Locação de porta fechada" in m["message"] for m in zapi_outbox)
    assert not SdrTask.objects(customer=lead, status="pending").count()  # cadência acabou


@pytest.mark.django_db
@pytest.mark.parametrize("target,proposal_status", [(domain.LOST, "recusada"), (domain.PROPOSAL_SENT, "enviada")])
def test_leaving_accepted_releases_the_reserved_stock(sdr_api, stock, contacts, target, proposal_status):
    lead = porta_lead()
    proposal = sent_proposal(sdr_api, lead)
    assert sdr_api.post(f"/api/v1/sales/proposals/{proposal['id']}/accept/").status_code == 200
    extra = {"lost_reason": "desistiu"} if target == domain.LOST else {}
    resp = stage(sdr_api, lead, target, **extra)
    assert resp.status_code == 200, resp.data
    assert Proposal.objects.get(id=proposal["id"]).status == proposal_status
    assert not InventoryReservation.objects(proposal_id=proposal["id"], status="reservado").count()
    lead.reload()
    assert lead.owner == "sdr"
    assert ServiceLog.objects(customer=lead, description__contains="Aceite da proposta v1 desfeito").count() == 1


@pytest.mark.django_db
def test_contract_lost_after_signing_releases_stock(api_client, stock, contacts):
    lead = porta_lead()
    proposal = sent_proposal(api_client, lead)
    api_client.post(f"/api/v1/sales/proposals/{proposal['id']}/accept/")
    assert stage(api_client, lead, domain.CONTRACT_SIGNED).status_code == 200
    assert stage(api_client, lead, domain.LOST, lost_reason="desistiu").status_code == 200
    assert not InventoryReservation.objects(proposal_id=proposal["id"], status="reservado").count()


@pytest.mark.django_db
def test_accepting_rechecks_stock_so_the_same_weekend_is_not_sold_twice(sdr_api, api_client, stock, contacts):
    first, second = porta_lead(), porta_lead(phone="5562977776666", name="Marta")
    p1 = sent_proposal(sdr_api, first)
    p2 = sent_proposal(sdr_api, second)  # calculada antes do aceite da primeira: passou no estoque
    assert sdr_api.post(f"/api/v1/sales/proposals/{p1['id']}/accept/").status_code == 200

    refused = sdr_api.post(f"/api/v1/sales/proposals/{p2['id']}/accept/")
    assert refused.status_code == 400 and "Estoque insuficiente" in refused.data["detail"]
    assert "Torre Q30 5 m" in refused.data["detail"]
    assert Proposal.objects.get(id=p2["id"]).status == "enviada"
    second.reload()
    assert second.customer_state_now == domain.PROPOSAL_SENT
    # Pelo card também não passa
    assert stage(sdr_api, second, domain.PROPOSAL_ACCEPTED).status_code == 400

    # A Erica decide aceitar mesmo assim (ex.: vai sublocar): fica registrado na linha do tempo
    forced = api_client.post(f"/api/v1/sales/proposals/{p2['id']}/accept/")
    assert forced.status_code == 200
    assert ServiceLog.objects(customer=second, description__contains="com falta de estoque").count() == 1


@pytest.mark.django_db
def test_new_version_cannot_replace_a_proposal_of_another_customer(sdr_api, stock):
    mine, other = porta_lead(), porta_lead(phone="5562977776666", name="Marta")
    theirs = sdr_api.post("/api/v1/sales/proposals/", {"customer_id": str(other.id), "mode": "porta", "inputs": PORTA},
                          format="json").data
    resp = sdr_api.post("/api/v1/sales/proposals/", {"customer_id": str(mine.id), "mode": "porta", "inputs": PORTA,
                                                     "replaces": theirs["id"]}, format="json")
    assert resp.status_code == 400
    assert Proposal.objects.get(id=theirs["id"]).status == "rascunho"


@pytest.mark.django_db
def test_proposals_of_an_archived_lead_cannot_be_sent_or_accepted(sdr_api, stock):
    lead = porta_lead()
    draft = sdr_api.post("/api/v1/sales/proposals/", {"customer_id": str(lead.id), "mode": "porta", "inputs": PORTA},
                         format="json").data
    assert stage(sdr_api, lead, domain.LOST, lost_reason="preco").status_code == 200
    # Contato volta com outro pedido: o lead perdido vai para o histórico
    assert sdr_api.post(f"/api/v1/crm/contacts/{lead.id}/new-lead/", {"product": "corporativo"},
                        format="json").status_code == 200
    resp = sdr_api.post(f"/api/v1/sales/proposals/{draft['id']}/send/")
    assert resp.status_code == 400 and "lead anterior" in resp.data["detail"]
    lead.reload()
    assert lead.customer_state_now == domain.NEW_LEAD and lead.quoted_amount == 0


# --- Calculadora: valores digitados ------------------------------------------------------------

@pytest.mark.django_db
@pytest.mark.parametrize("field,value", [
    ("manual_freight", -5000), ("project_cost", -100), ("discount", -50), ("extra_mics", -2),
])
def test_negative_values_never_become_a_hidden_discount(sdr_api, field, value):
    inputs = {"guests": 100, "event_date": "2026-11-20", "margin": 0.35, "with_invoice": True, field: value}
    resp = sdr_api.post("/api/v1/sales/proposals/calculate/", {"mode": "corporativo", "inputs": inputs}, format="json")
    assert resp.status_code == 400, resp.data
    assert "negativo" in resp.data["detail"]


@pytest.mark.django_db
def test_porta_rejects_negative_quantity_and_unknown_items(sdr_api):
    base = {"pickup_date": "2026-10-23", "return_date": "2026-10-26"}
    for items in ([{"code": "q30_torre_5m", "qty": -3}], [{"code": "peca_inventada", "qty": 1}],
                  [{"code": "q30_torre_5m", "qty": "muitas"}], [{"code": "q30_torre_5m", "qty": "Infinity"}]):
        resp = sdr_api.post("/api/v1/sales/proposals/calculate/", {"mode": "porta", "inputs": {**base, "items": items}},
                            format="json")
        assert resp.status_code == 400, (items, resp.status_code)
    single = sdr_api.post("/api/v1/sales/proposals/calculate/", {"mode": "produto_unico", "inputs": {
        "event_date": "2026-11-21", "items": [{"code": "palco_praticavel_2x1", "qty": 1}], "manual_freight": -300}},
        format="json")
    assert single.status_code == 400


@pytest.mark.django_db
def test_return_before_pickup_is_refused(sdr_api):
    inputs = {"pickup_date": "2026-10-26", "return_date": "2026-10-23", "items": [{"code": "q30_torre_5m", "qty": 1}]}
    resp = sdr_api.post("/api/v1/sales/proposals/calculate/", {"mode": "porta", "inputs": inputs}, format="json")
    assert resp.status_code == 400 and "devolução" in resp.data["detail"]


@pytest.mark.django_db
def test_margin_must_be_one_of_the_configured_levels(sdr_api):
    inputs = {"guests": 100, "event_date": "2026-11-20", "margin": 0.05, "with_invoice": True}
    resp = sdr_api.post("/api/v1/sales/proposals/calculate/", {"mode": "corporativo", "inputs": inputs}, format="json")
    assert resp.status_code == 400 and "Margem" in resp.data["detail"]


# --- Qualificação ----------------------------------------------------------------------------

@pytest.mark.django_db
@pytest.mark.parametrize("current", [domain.PROPOSAL_SENT, domain.PROPOSAL_ACCEPTED, domain.CONTRACT_SIGNED])
def test_qualify_again_never_moves_a_lead_back(api_client, current):
    lead = Customer(name="Ana", phone="5562911112222", customer_state_now=current, product="corporativo",
                    proposal_sent_at=datetime(2026, 10, 18)).save()
    resp = api_client.post(f"/api/v1/crm/customers/{lead.id}/qualification/qualify/",
                           {"pending_fields": ["horario_montagem"], "needs_erica": True}, format="json")
    assert resp.status_code == 200
    assert resp.data["customer_state_now"] == current
    assert "horario_montagem" in resp.data["pending_fields"] and "aguardando_erica" in resp.data["flags"]
    assert not SdrTask.objects(customer=lead, type="ligar_15min").count()


@pytest.mark.django_db
def test_partner_never_enters_the_sdr_queue_from_any_path(api_client):
    partner = Customer(name="Parceiro", phone="5562911112222", human_operator=True, owner="erica",
                       contact_type="parceiro", product="estrutura_porta").save()
    api_client.post(f"/api/v1/crm/customers/{partner.id}/qualification/qualify/", {}, format="json")
    from crm.container import CrmContainer
    tasks = CrmContainer.get_sdr_task_service()
    tasks.create_stale_lead_tasks(now=datetime(2026, 10, 30))
    tasks.run_proposal_cadence(now=datetime(2026, 10, 30))
    assert SdrTask.objects(customer=partner).count() == 0
    board = api_client.get("/api/v1/crm/funnel/").data
    assert all(c["id"] != str(partner.id) for col in board.values() for c in col["results"])
    assert all(t["customer_id"] != str(partner.id) for t in api_client.get("/api/v1/crm/tasks/").data)


@pytest.mark.django_db
def test_lost_requires_a_valid_reason(sdr_api):
    lead = Customer(name="Ana", phone="5562911112222", customer_state_now=domain.QUALIFIED).save()
    assert stage(sdr_api, lead, domain.LOST).status_code == 400
    assert stage(sdr_api, lead, domain.LOST, lost_reason="porque sim").status_code == 400
    assert stage(sdr_api, lead, domain.LOST, lost_reason="preco").status_code == 200


@pytest.mark.django_db
def test_sdr_cannot_sign_contracts_and_lucia_only_for_door_rental(sdr_api, porta_api):
    porta = Customer(name="Porta", phone="5562911112222", customer_state_now=domain.PROPOSAL_ACCEPTED,
                     product="estrutura_porta").save()
    evento = Customer(name="Evento", phone="5562933334444", customer_state_now=domain.PROPOSAL_ACCEPTED,
                      product="corporativo").save()
    assert stage(sdr_api, porta, domain.CONTRACT_SIGNED).status_code == 403
    assert stage(porta_api, evento, domain.CONTRACT_SIGNED).status_code == 403
    assert stage(porta_api, porta, domain.CONTRACT_SIGNED).status_code == 200
    # Nem pelo formulário da tabela
    resp = sdr_api.patch(f"/api/v1/crm/customers/{evento.id}/", {"customer_state_now": domain.CONTRACT_SIGNED},
                         format="json")
    assert resp.status_code == 403


# --- Agenda da Erica ---------------------------------------------------------------------------

@pytest.fixture
def no_google(monkeypatch):
    monkeypatch.setattr("agenda.services.agenda_service.is_configured", lambda: False)


@pytest.mark.django_db
def test_sdr_cannot_book_over_training_or_another_meeting(sdr_api, no_google, zapi_outbox):
    lead = Customer(name="Paula", phone="5562955554444").save()
    other = Customer(name="Rita", phone="5562966665555").save()
    url = "/api/v1/agenda/events/"
    # Quarta 21/10, 12h em Brasília (15h UTC): treino da Erica
    training = {"type": "reuniao_online", "customer_id": str(lead.id),
                "start": "2026-10-21T15:00:00Z", "end": "2026-10-21T16:00:00Z", "force": True}
    resp = sdr_api.post(url, training, format="json")
    assert resp.status_code == 409 and resp.data["can_force"] is False  # force só vale para a Erica

    first = sdr_api.post(url, {"type": "visita_tecnica", "customer_id": str(other.id), "location": "Rua 10",
                               "start": "2026-10-22T13:00:00Z", "end": "2026-10-22T15:00:00Z"}, format="json")
    assert first.status_code == 201
    clash = sdr_api.post(url, {"type": "reuniao_online", "customer_id": str(lead.id),
                               "start": "2026-10-22T14:00:00Z", "end": "2026-10-22T15:00:00Z"}, format="json")
    assert clash.status_code == 409 and "Visita técnica" in clash.data["detail"]
    assert CalendarEvent.objects(customer=lead).count() == 0
    assert not any(m.get("phone") == lead.phone for m in zapi_outbox)  # cliente não recebe confirmação falsa

    past = sdr_api.post(url, {"type": "reuniao_online", "customer_id": str(lead.id),
                              "start": "2026-10-16T13:00:00Z", "end": "2026-10-16T14:00:00Z"}, format="json")
    assert past.status_code == 400 and "passado" in past.data["detail"]
    free = sdr_api.post(url, {"type": "reuniao_online", "customer_id": str(lead.id),
                              "start": "2026-10-22T17:00:00Z", "end": "2026-10-22T18:00:00Z"}, format="json")
    assert free.status_code == 201


# --- Escrita formal e sem emoji (regra 5) --------------------------------------------------------

def test_quick_replies_are_formal_and_without_emoji():
    for reply in DEFAULT_QUICK_REPLIES:
        assert not EMOJI.search(reply["text"]) and not EMOJI.search(reply["title"])
        assert "!" not in reply["text"]


@pytest.mark.django_db
def test_automatic_notices_have_no_emoji(api_client, stock, contacts, zapi_outbox, no_google):
    lead = porta_lead()
    api_client.post(f"/api/v1/crm/customers/{lead.id}/qualification/qualify/", {"needs_erica": True}, format="json")
    locked = {**PORTA, "pickup_date": "2026-10-16"}  # 10 dias: trava para aprovação
    api_client.post("/api/v1/sales/proposals/", {"customer_id": str(lead.id), "mode": "porta", "inputs": locked},
                    format="json")
    proposal = sent_proposal(api_client, lead)
    api_client.post(f"/api/v1/sales/proposals/{proposal['id']}/accept/")
    api_client.post("/api/v1/agenda/events/", {"type": "reuniao_online", "customer_id": str(lead.id),
                                              "start": "2026-10-22T17:00:00Z", "end": "2026-10-22T18:00:00Z"},
                    format="json")
    partner = Customer(name="Parceiro", phone="5562911110002").save()
    api_client.post(f"/api/v1/crm/customers/{partner.id}/human-operator/", {"reason": "cliente antigo"}, format="json")

    destinations = {m.get("phone") for m in zapi_outbox}
    assert {"5562900000001", "5562900000002", "5562900000003", "120363000000000000-group", lead.phone} <= destinations
    for message in zapi_outbox:
        text = message.get("message") or message.get("caption") or ""
        assert not EMOJI.search(text), text


# --- Datas em UTC --------------------------------------------------------------------------------

@pytest.mark.django_db
def test_timestamps_are_utc_even_on_a_server_in_brasilia_time(api_client, stock, contacts):
    """Com o relógio do servidor em Brasília, a conversa que recebeu o PDF caía 3 h na lista."""
    from chat.models.conversation_model import ConversationModel
    with freeze_time("2026-10-19 13:00:00", tz_offset=-3):
        lead = porta_lead()
        conversation = ConversationModel(customer=lead).save()
        draft = api_client.post("/api/v1/sales/proposals/", {"customer_id": str(lead.id), "mode": "porta",
                                                             "inputs": PORTA}, format="json").data
    with freeze_time("2026-10-19 14:00:00", tz_offset=-3):
        assert api_client.post(f"/api/v1/sales/proposals/{draft['id']}/send-whatsapp/").status_code == 200
    conversation.reload()
    assert conversation.updated_at == datetime(2026, 10, 19, 14, 0)


def test_model_defaults_are_utc():
    """Padrões de created_at/updated_at em UTC (o relógio do servidor pode estar em Brasília)."""
    from chat.models.conversation_model import ConversationModel
    for model in (Customer, ConversationModel):
        for name in ("created_at", "updated_at"):
            assert model._fields[name].default.__name__ == "utcnow", (model.__name__, name)
