"""Funil zerado: só entra quem a IA atende/qualifica ou quem tem lead aberto à mão."""
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
def test_new_ai_conversation_puts_contact_in_funnel_but_not_partners():
    lead = Customer(name="Nova", phone="5562900000001").save()
    partner = Customer(name="Parceiro", phone="5562900000002", human_operator=True).save()
    supplier = Customer(name="Fornecedor", phone="5562900000003", contact_type="fornecedor").save()
    for customer in (lead, partner, supplier):
        ConversationRepository.create_conversation(customer)
    for customer in (lead, partner, supplier):
        customer.reload()
    assert lead.funnel_entered_at is not None
    assert partner.funnel_entered_at is None and supplier.funnel_entered_at is None

    # Entrar de novo não muda a data
    first = lead.funnel_entered_at
    ConversationRepository.create_conversation(lead)
    lead.reload()
    assert lead.funnel_entered_at == first


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
