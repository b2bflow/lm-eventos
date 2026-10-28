"""Aba "Arquivados" do funil (ganhos e perdidos arquivados) e exclusão de proposta com o PDF."""
from datetime import datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from crm import domain
from crm.models.custumer_model import Customer
from crm.models.log_service_model import ServiceLog
from crm.models.sdr_task_model import SdrTask
from inventory.models import InventoryReservation
from sales.models import Proposal

FUNNEL = "/api/v1/crm/funnel/"
PORTA_INPUTS = {"pickup_date": "2026-10-23", "return_date": "2026-10-26",
                "items": [{"code": "q30_torre_5m", "qty": 100}, {"code": "q30_cubo_5_faces", "qty": 8}]}


def _lead(stage=domain.QUALIFIED, phone="5562900000101", product="estrutura_porta", **extra):
    return Customer(name="Arquivo", phone=phone, customer_state_now=stage, product=product,
                    funnel_entered_at=datetime.utcnow(), **extra).save()


def _card_ids(board, stage):
    return [card["id"] for card in board[stage]["results"]]


# --- Arquivar ---------------------------------------------------------------------------------

@pytest.mark.django_db
def test_archive_as_lost_moves_card_to_archived_tab(sdr_api):
    lead = _lead()
    SdrTask(customer=lead, type="ligar_15min", due_at=datetime.utcnow()).save()

    no_reason = sdr_api.post(f"/api/v1/crm/customers/{lead.id}/archive/", {"result": "perdido"}, format="json")
    assert no_reason.status_code == 400  # perder exige o motivo

    resp = sdr_api.post(f"/api/v1/crm/customers/{lead.id}/archive/",
                        {"result": "perdido", "lost_reason": "preco"}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["customer_state_now"] == domain.LOST and resp.data["funnel_archived_at"]
    lead.reload()
    assert lead.lost_reason == "preco"
    assert SdrTask.objects(customer=lead, status="pending").count() == 0
    assert ServiceLog.objects(customer=lead, action_type="FUNNEL_ARCHIVED").count() == 1

    active = sdr_api.get(FUNNEL).data
    assert set(active) == set(domain.BOARD_STAGES) and active[domain.LOST]["count"] == 0
    archived = sdr_api.get(FUNNEL, {"archived": "true"}).data
    assert set(archived) == {domain.CONTRACT_SIGNED, domain.LOST}
    assert _card_ids(archived, domain.LOST) == [str(lead.id)]
    listed = sdr_api.get(f"{FUNNEL}list/", {"archived": "true"}).data
    assert [card["id"] for card in listed["results"]] == [str(lead.id)]
    assert sdr_api.get(f"{FUNNEL}list/").data["count"] == 0

    again = sdr_api.post(f"/api/v1/crm/customers/{lead.id}/archive/", {"result": "perdido"}, format="json")
    assert again.status_code == 400


@pytest.mark.django_db
def test_archive_as_won_follows_stage_rules(api_client, sdr_api):
    # Card anda livre: dá para registrar ganho em qualquer etapa (com o papel certo)
    early = _lead(domain.QUALIFIED)
    resp = api_client.post(f"/api/v1/crm/customers/{early.id}/archive/", {"result": "ganho"}, format="json")
    assert resp.status_code == 200, resp.data
    early.reload()
    assert early.funnel_archived_at is not None and early.stage == domain.CONTRACT_SIGNED

    signed = _lead(domain.CONTRACT_SIGNED, phone="5562900000102")
    resp = sdr_api.post(f"/api/v1/crm/customers/{signed.id}/archive/", {"result": "ganho"}, format="json")
    assert resp.status_code == 200, resp.data
    assert str(signed.id) in _card_ids(sdr_api.get(FUNNEL, {"archived": "1"}).data, domain.CONTRACT_SIGNED)

    accepted = _lead(domain.PROPOSAL_ACCEPTED, phone="5562900000103", product="corporativo")
    denied = sdr_api.post(f"/api/v1/crm/customers/{accepted.id}/archive/", {"result": "ganho"}, format="json")
    assert denied.status_code == 403  # contrato de evento é com a Erica
    ok = api_client.post(f"/api/v1/crm/customers/{accepted.id}/archive/", {"result": "ganho"}, format="json")
    assert ok.status_code == 200 and ok.data["customer_state_now"] == domain.CONTRACT_SIGNED


@pytest.mark.django_db
def test_unarchive_and_reopening_bring_card_back(sdr_api):
    lead = _lead(domain.LOST, lost_reason="preco", funnel_archived_at=datetime.utcnow())
    resp = sdr_api.post(f"/api/v1/crm/customers/{lead.id}/unarchive/")
    assert resp.status_code == 200 and resp.data["funnel_archived_at"] is None
    assert _card_ids(sdr_api.get(FUNNEL).data, domain.LOST) == [str(lead.id)]
    assert sdr_api.post(f"/api/v1/crm/customers/{lead.id}/unarchive/").status_code == 400

    # Reabrir um perdido arquivado (voltar a uma etapa em andamento) devolve o card aos ativos
    lead.update(set__funnel_archived_at=datetime.utcnow())
    resp = sdr_api.post(f"/api/v1/crm/customers/{lead.id}/stage/", {"stage": domain.QUALIFIED}, format="json")
    assert resp.status_code == 200, resp.data
    lead.reload()
    assert lead.funnel_archived_at is None
    assert _card_ids(sdr_api.get(FUNNEL).data, domain.QUALIFIED) == [str(lead.id)]


@pytest.mark.django_db
def test_new_lead_for_archived_contact_starts_active():
    from crm.services.contact_service import ContactService
    lead = _lead(domain.LOST, lost_reason="preco", funnel_archived_at=datetime.utcnow())
    ContactService().start_new_lead(str(lead.id), "corporativo")
    lead.reload()
    assert lead.stage == domain.QUALIFIED and lead.funnel_archived_at is None and lead.funnel_entered_at


# --- Excluir proposta ---------------------------------------------------------------------------

@pytest.fixture
def stock():
    call_command("seed_inventory", stdout=StringIO())


def _save(client, lead, qty=100):
    body = {"customer_id": str(lead.id), "mode": "porta",
            "inputs": {**PORTA_INPUTS, "items": [{"code": "q30_torre_5m", "qty": qty}]}}
    resp = client.post("/api/v1/sales/proposals/", body, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


@pytest.mark.django_db
def test_delete_draft_removes_proposal_and_pdf(sdr_api, stock):
    lead = _lead()
    draft = _save(sdr_api, lead)
    assert sdr_api.get(f"/api/v1/sales/proposals/{draft['id']}/pdf/").status_code == 200

    resp = sdr_api.delete(f"/api/v1/sales/proposals/{draft['id']}/")
    assert resp.status_code == 200, resp.data
    assert Proposal.objects(id=draft["id"]).count() == 0
    assert sdr_api.get(f"/api/v1/sales/proposals/{draft['id']}/pdf/").status_code == 404
    assert sdr_api.get(FUNNEL).data[domain.QUALIFIED]["results"][0]["current_proposal"] is None
    log = ServiceLog.objects(customer=lead, action_type="PROPOSAL_DELETED").first()
    assert log and "v1" in log.description
    assert sdr_api.delete(f"/api/v1/sales/proposals/{draft['id']}/").status_code == 400


@pytest.mark.django_db
def test_deleting_current_version_restores_previous_one(sdr_api, stock):
    lead = _lead()
    first = _save(sdr_api, lead, qty=100)
    sdr_api.post(f"/api/v1/sales/proposals/{first['id']}/send/")
    second = sdr_api.post("/api/v1/sales/proposals/", {
        "customer_id": str(lead.id), "mode": "porta", "replaces": first["id"],
        "inputs": {**PORTA_INPUTS, "items": [{"code": "q30_torre_5m", "qty": 10}]}}, format="json").data
    assert Proposal.objects.get(id=first["id"]).status == "substituida"

    resp = sdr_api.delete(f"/api/v1/sales/proposals/{second['id']}/")
    assert resp.status_code == 200, resp.data
    assert resp.data["restored"]["id"] == first["id"] and resp.data["restored"]["status"] == "enviada"
    card = sdr_api.get(FUNNEL).data[domain.PROPOSAL_SENT]["results"][0]
    assert card["current_proposal"]["id"] == first["id"] and card["quoted_amount"] == first["total"]


@pytest.mark.django_db
def test_deleting_only_sent_proposal_reverts_stage_and_tasks(sdr_api, stock):
    from crm.models.quote_model import Quote
    lead = _lead()
    quote = Quote(customer=lead, status="BUDGET", quoted_amount=999).save()
    proposal = _save(sdr_api, lead)
    sdr_api.post(f"/api/v1/sales/proposals/{proposal['id']}/send/")
    SdrTask(customer=lead, type="follow_up_d1", due_at=datetime.utcnow() + timedelta(days=1)).save()
    lead.reload()
    assert lead.stage == domain.PROPOSAL_SENT and lead.quoted_amount == proposal["total"]

    assert sdr_api.delete(f"/api/v1/sales/proposals/{proposal['id']}/").status_code == 200
    lead.reload()
    quote.reload()
    assert lead.stage == domain.QUALIFIED and lead.proposal_sent_at is None
    assert lead.quoted_amount == 0 and quote.quoted_amount == 0
    assert SdrTask.objects(customer=lead, status="pending", type__in=["proposta_vencendo", "follow_up_d1"]).count() == 0


@pytest.mark.django_db
def test_accepted_proposal_cannot_be_deleted(sdr_api, stock):
    lead = _lead()
    proposal = _save(sdr_api, lead)
    sdr_api.post(f"/api/v1/sales/proposals/{proposal['id']}/send/")
    assert sdr_api.post(f"/api/v1/sales/proposals/{proposal['id']}/accept/").status_code == 200

    resp = sdr_api.delete(f"/api/v1/sales/proposals/{proposal['id']}/")
    assert resp.status_code == 400 and "aceita" in resp.data["detail"]
    assert Proposal.objects(id=proposal["id"]).count() == 1
    assert InventoryReservation.objects(proposal_id=proposal["id"], status="reservado").count() > 0


@pytest.mark.django_db
def test_deleting_locked_proposal_clears_approval_flag(sdr_api, stock):
    lead = _lead()
    locked = sdr_api.post("/api/v1/sales/proposals/", {"customer_id": str(lead.id), "mode": "porta", "inputs": {
        **PORTA_INPUTS, "final_total": 100}}, format="json").data
    assert locked["status"] == "aguardando_aprovacao"
    lead.reload()
    assert "aguardando_aprovacao_desconto" in lead.flags

    assert sdr_api.delete(f"/api/v1/sales/proposals/{locked['id']}/").status_code == 200
    lead.reload()
    assert "aguardando_aprovacao_desconto" not in lead.flags
