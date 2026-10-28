"""Funil zerado: só entra quem a IA qualifica ou quem tem lead aberto à mão."""
from datetime import datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from chat.models.conversation_model import ConversationModel
from chat.repositories.conversation_repository import ConversationRepository
from crm import domain
from crm.container import CrmContainer
from crm.models.custumer_model import Customer
from crm.models.opportunity_model import Opportunity
from crm.models.quote_model import Quote
from crm.services.quote_service import QuoteService

CONVERSATIONS = "/api/v1/chat/conversations/"


@pytest.mark.django_db
def test_new_ai_conversation_does_not_put_contact_in_funnel():
    """Só entra no funil quem a IA qualifica (reunião com o Marcelo, 28/10): conversa nova não basta."""
    lead = Customer(name="Nova", phone="5562900000001").save()
    ConversationRepository.create_conversation(lead)
    lead.reload()
    assert lead.funnel_entered_at is None


@pytest.mark.django_db
def test_ai_qualification_skips_partners_and_suppliers():
    partner = Customer(name="Parceiro", phone="5562900000002", human_operator=True).save()
    supplier = Customer(name="Fornecedor", phone="5562900000003", contact_type="fornecedor").save()
    for customer in (partner, supplier):
        quote = Quote(customer=customer, status="ANALYSIS").save()
        QuoteService().update_quote(str(quote.id), {"status": "WAITING_BUDGET"})
        customer.reload()
        assert customer.funnel_entered_at is None


@pytest.mark.django_db
def test_ai_waiting_budget_marks_lead_as_ai_qualified():
    customer = Customer(name="Ana", phone="5562900000010").save()
    quote = Quote(customer=customer, status="ANALYSIS").save()
    QuoteService().update_quote(str(quote.id), {"status": "WAITING_BUDGET", "guest_count": 120})
    customer.reload()
    assert customer.ai_qualified_at is not None and customer.funnel_entered_at is not None
    assert customer.stage == domain.QUALIFIED


@pytest.mark.django_db
def test_human_quote_edit_is_not_ai_qualification(admin_user):
    customer = Customer(name="Bia", phone="5562900000011").save()
    quote = Quote(customer=customer, status="ANALYSIS").save()
    QuoteService().update_quote(str(quote.id), {"status": "WAITING_BUDGET"}, user=admin_user)
    customer.reload()
    assert customer.ai_qualified_at is None


@pytest.mark.django_db
def test_convert_old_contact_archives_stale_lead_and_opens_new_one(api_client):
    old = Customer(name="Antigo", phone="5562900000020", product="corporativo", customer_state_now="QUALIFIED",
                   quoted_amount=3000, created_at=datetime.utcnow() - timedelta(days=90)).save()
    resp = api_client.post(f"/api/v1/crm/contacts/{old.id}/new-lead/", {"product": "social"}, format="json")
    assert resp.status_code in (200, 201), resp.data
    old.reload()
    assert old.funnel_entered_at is not None and old.product == "social" and old.stage == domain.NEW_LEAD
    assert old.quoted_amount == 0
    assert Opportunity.objects.get(customer=old).stage == domain.QUALIFIED

    board = api_client.get("/api/v1/crm/funnel/").data
    assert [c["id"] for c in board[domain.NEW_LEAD]["results"]] == [str(old.id)]


@pytest.mark.django_db
def test_reset_funnel_empties_board(api_client):
    Customer(name="No funil", phone="5562900000030", funnel_entered_at=datetime.utcnow()).save()
    out = StringIO()
    call_command("reset_funnel", stdout=out)
    assert "1 contato" in out.getvalue()
    assert Customer.objects(funnel_entered_at__ne=None).count() == 0
    board = api_client.get("/api/v1/crm/funnel/").data
    assert sum(col["count"] for col in board.values()) == 0


@pytest.mark.django_db
def test_sdr_queue_ignores_leads_outside_funnel(api_client):
    service = CrmContainer.get_sdr_task_service()
    inside = Customer(name="Dentro", phone="5562900000040", funnel_entered_at=datetime.utcnow()).save()
    outside = Customer(name="Fora", phone="5562900000041").save()
    service.create_task(str(inside.id), "ligar_15min", due_at=datetime.utcnow())
    service.create_task(str(outside.id), "ligar_15min", due_at=datetime.utcnow())
    tasks = api_client.get("/api/v1/crm/tasks/").data
    assert [t["customer_id"] for t in tasks] == [str(inside.id)]


@pytest.mark.django_db
def test_conversation_filters_by_attendance_and_ai_qualification(api_client):
    ai = Customer(name="Com IA", phone="5562900000050").save()
    transferred = Customer(name="Transferido", phone="5562900000051", ai_qualified_at=datetime.utcnow()).save()
    manual = Customer(name="Manual", phone="5562900000052").save()
    ConversationModel(customer=ai, tag="AGENTE").save()
    ConversationModel(customer=transferred, tag="operador humano").save()  # gravado pela IA ao transferir
    ConversationModel(customer=manual, tag="OPERADOR").save()

    def names(params):
        return sorted(c["customer_name"] for c in api_client.get(CONVERSATIONS, params).data["results"])

    assert names({"tag": "AGENTE"}) == ["Com IA"]
    assert names({"tag": "OPERADOR"}) == ["Manual", "Transferido"]
    assert names({"ai_qualified": "true"}) == ["Transferido"]
    item = api_client.get(CONVERSATIONS, {"ai_qualified": "true"}).data["results"][0]
    assert item["customer_ai_qualified_at"] is not None


@pytest.mark.django_db
def test_saving_a_proposal_puts_lead_in_funnel(api_client):
    customer = Customer(name="Calc", phone="5562900000060").save()
    resp = api_client.post("/api/v1/sales/proposals/", {
        "customer_id": str(customer.id), "mode": "corporativo",
        "inputs": {"guests": 80, "event_date": "2026-12-10", "operational": ["carga"]},
    }, format="json")
    assert resp.status_code == 201, resp.data
    customer.reload()
    assert customer.funnel_entered_at is not None


@pytest.mark.django_db
def test_funnel_card_carries_the_current_proposal_pdf(api_client):
    customer = Customer(name="Ana Card", phone="5562900000061").save()
    body = {"customer_id": str(customer.id), "mode": "corporativo",
            "inputs": {"guests": 80, "event_date": "2026-12-10", "operational": ["carga"]}}
    api_client.post("/api/v1/sales/proposals/", body, format="json")
    second = api_client.post("/api/v1/sales/proposals/", body, format="json").data

    def card(data):
        return next(c for column in data.values() for c in column["results"] if c["id"] == str(customer.id))

    current = card(api_client.get("/api/v1/crm/funnel/").data)["current_proposal"]
    assert current["id"] == second["id"] and current["version"] == 2
    assert current["file_name"] == "Proposta_LM_Ana_Card_v2.pdf" and current["status"] == second["status"]
    listed = api_client.get("/api/v1/crm/funnel/list/").data["results"]
    assert next(c for c in listed if c["id"] == str(customer.id))["current_proposal"]["id"] == second["id"]
    other = Customer(name="Sem proposta", phone="5562900000062", funnel_entered_at=datetime.utcnow()).save()
    assert next(c for c in api_client.get("/api/v1/crm/funnel/list/").data["results"]
                if c["id"] == str(other.id))["current_proposal"] is None


@pytest.mark.django_db
def test_funnel_list_view_uses_board_rules_and_paginates(api_client):
    now = datetime.utcnow()
    for i in range(3):
        Customer(name=f"Lead {i}", phone=f"556291000000{i}", funnel_entered_at=now, product="social",
                 customer_state_now=domain.QUALIFIED).save()
    Customer(name="Antigo", phone="5562910000009").save()  # fora do funil zerado
    Customer(name="Parceiro", phone="5562910000008", funnel_entered_at=now, human_operator=True).save()

    data = api_client.get("/api/v1/crm/funnel/list/", {"limit": 2}).data
    assert data["count"] == 3 and len(data["results"]) == 2 and data["has_more"]
    page2 = api_client.get("/api/v1/crm/funnel/list/", {"limit": 2, "offset": 2}).data
    assert len(page2["results"]) == 1 and not page2["has_more"]
    assert api_client.get("/api/v1/crm/funnel/list/", {"stage": domain.LOST}).data["count"] == 0
    assert api_client.get("/api/v1/crm/funnel/list/", {"stage": "XX"}).status_code == 400
    assert api_client.get("/api/v1/crm/funnel/list/", {"include_human": "true"}).data["count"] == 4


@pytest.mark.django_db
def test_lead_page_creates_activity_and_completes_it(api_client):
    lead = Customer(name="Lu", phone="5562910000100", funnel_entered_at=datetime.utcnow()).save()
    url = f"/api/v1/crm/customers/{lead.id}/tasks/"
    resp = api_client.post(url, {"type": "atividade_reuniao", "title": "Visita ao salão",
                                 "due_at": "2026-10-30T14:00:00-03:00"}, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["label"] == "Reunião: Visita ao salão"
    assert resp.data["due_at"].startswith("2026-10-30T17:00")  # gravado em UTC
    assert [t["id"] for t in api_client.get(url).data] == [resp.data["id"]]
    assert api_client.post(f"/api/v1/crm/tasks/{resp.data['id']}/done/").status_code == 200
    assert api_client.get(url, {"status": "done"}).data[0]["title"] == "Visita ao salão"

    assert api_client.post(url, {"type": "ligar_15min", "title": "x", "due_at": "2026-10-30"}, format="json").status_code == 400
    assert api_client.post(url, {"type": "atividade_tarefa", "title": " ", "due_at": "2026-10-30"}, format="json").status_code == 400


@pytest.mark.django_db
def test_contact_with_stale_lead_can_open_a_new_one(api_client):
    """Lead de antes do funil zerado aparece no histórico do contato, mas não trava o "Abrir lead"."""
    old = Customer(name="Antigo", phone="5562900000070", product="corporativo",
                   customer_state_now="PROPOSAL_SENT").save()
    detail = api_client.get(f"/api/v1/crm/contacts/{old.id}/").data
    assert detail["in_funnel"] is False and detail["current_lead_open"] is False
    assert [lead["stage"] for lead in detail["leads"]] == ["PROPOSAL_SENT"]

    old.update(set__funnel_entered_at=datetime.utcnow())
    detail = api_client.get(f"/api/v1/crm/contacts/{old.id}/").data
    assert detail["in_funnel"] is True and detail["current_lead_open"] is True


@pytest.mark.django_db
def test_remove_from_funnel_keeps_contact_and_cancels_tasks(sdr_api):
    from crm.models.log_service_model import ServiceLog
    from crm.models.sdr_task_model import SdrTask
    lead = Customer(name="Sai", phone="5562900000040", funnel_entered_at=datetime.utcnow()).save()
    SdrTask(customer=lead, type="ligar_15min", due_at=datetime.utcnow()).save()

    resp = sdr_api.post(f"/api/v1/crm/customers/{lead.id}/remove-from-funnel/")
    assert resp.status_code == 200, resp.data
    lead.reload()
    assert lead.funnel_entered_at is None
    assert SdrTask.objects(customer=lead, status="pending").count() == 0
    assert ServiceLog.objects(customer=lead, action_type="FUNNEL_REMOVED").count() == 1
    board = sdr_api.get("/api/v1/crm/funnel/").data
    assert board[domain.NEW_LEAD]["count"] == 0
    # O contato continua na página Contatos
    assert sdr_api.get(f"/api/v1/crm/contacts/{lead.id}/").status_code == 200

    again = sdr_api.post(f"/api/v1/crm/customers/{lead.id}/remove-from-funnel/")
    assert again.status_code == 400


@pytest.mark.django_db
def test_remove_from_funnel_blocks_accepted_proposal(api_client):
    lead = Customer(name="Aceito", phone="5562900000041", funnel_entered_at=datetime.utcnow(),
                    customer_state_now=domain.PROPOSAL_ACCEPTED).save()
    resp = api_client.post(f"/api/v1/crm/customers/{lead.id}/remove-from-funnel/")
    assert resp.status_code == 400
    lead.reload()
    assert lead.funnel_entered_at is not None


@pytest.mark.django_db
def test_lead_detail_exposes_funnel_dates(api_client):
    lead = Customer(name="Card", phone="5562900000042", funnel_entered_at=datetime.utcnow(),
                    ai_qualified_at=datetime.utcnow()).save()
    data = api_client.get(f"/api/v1/crm/customers/{lead.id}/").data
    assert data["funnel_entered_at"] and data["ai_qualified_at"]
