"""Reunião com o Marcelo (19/11): quem clica em "Solicitar orçamento" entra no funil na hora (coluna
"Pediu orçamento"), mesmo sem terminar a qualificação com a IA, e o WhatsApp filtra "Orçamentos IA"."""
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from crm import domain
from crm.models.custumer_model import Customer
from crm.models.log_service_model import ServiceLog
from crm.models.opportunity_model import Opportunity
from crm.models.quote_model import Quote
from crm.services.funnel_entry import mark_quote_requested
from crm.services.quote_service import QuoteService

WEBHOOK = "/api/v1/gateway/webhook/zapi/?token=test-webhook-token"
CONVERSATIONS = "/api/v1/chat/conversations/"
PHONE = "5562999991234"


@pytest.fixture
def ai_task():
    with patch("events.tasks.trigger_ai_agent_task.apply_async") as task:
        yield task


def post(payload):
    resp = APIClient().post(WEBHOOK, {"phone": PHONE, "isGroup": False, "status": "RECEIVED",
                                      "senderName": "Ana", **payload}, format="json")
    assert resp.status_code == 200, resp.data
    return resp


def click(button_id, label):
    return post({"buttonsResponseMessage": {"buttonId": button_id, "message": label}})


def board_ids(api_client, stage):
    return [card["id"] for card in api_client.get("/api/v1/crm/funnel/").data[stage]["results"]]


@pytest.mark.django_db
def test_quote_button_puts_lead_in_pediu_orcamento(ai_task, api_client):
    post({"text": {"message": "Olá"}})
    customer = Customer.objects.get(phone=PHONE)
    assert customer.funnel_entered_at is None

    click("1", "Solicitar orçamento")
    customer.reload()
    assert customer.quote_requested_at is not None and customer.funnel_entered_at is not None
    assert customer.stage == domain.NEW_LEAD

    board = api_client.get("/api/v1/crm/funnel/").data
    assert board[domain.NEW_LEAD]["label"] == "Pediu orçamento"
    assert [c["id"] for c in board[domain.NEW_LEAD]["results"]] == [str(customer.id)]
    assert board[domain.NEW_LEAD]["results"][0]["quote_requested_at"]
    # A coluna é a primeira do quadro e também filtra na lista
    assert list(board)[0] == domain.NEW_LEAD
    listed = api_client.get("/api/v1/crm/funnel/list/", {"stage": domain.NEW_LEAD}).data
    assert [c["id"] for c in listed["results"]] == [str(customer.id)]

    # "Voltar para menu" não registra outro pedido
    click("13", "Voltar para menu")
    assert ServiceLog.objects(customer=customer, action_type="QUOTE_REQUESTED").count() == 1


@pytest.mark.django_db
def test_other_menu_buttons_do_not_enter_funnel(ai_task):
    post({"text": {"message": "Olá"}})
    click("2", "Financeiro")
    customer = Customer.objects.get(phone=PHONE)
    assert customer.quote_requested_at is None and customer.funnel_entered_at is None


@pytest.mark.django_db
def test_ai_qualification_moves_card_to_lead_qualificado(ai_task, api_client):
    post({"text": {"message": "Olá"}})
    click("1", "Solicitar orçamento")
    customer = Customer.objects.get(phone=PHONE)

    quote = Quote.objects(customer=customer).first() or Quote(customer=customer, status="ANALYSIS").save()
    QuoteService().update_quote(str(quote.id), {"status": "WAITING_BUDGET"})
    customer.reload()
    assert customer.stage == domain.QUALIFIED and customer.ai_qualified_at is not None
    assert board_ids(api_client, domain.NEW_LEAD) == []
    assert board_ids(api_client, domain.QUALIFIED) == [str(customer.id)]


@pytest.mark.django_db
def test_lead_already_in_funnel_keeps_its_stage():
    lead = Customer(name="Andando", phone="5562900001001", funnel_entered_at=datetime.utcnow(),
                    customer_state_now=domain.PROPOSAL_SENT, product="social").save()
    assert mark_quote_requested(lead) == "marked"
    lead.reload()
    assert lead.stage == domain.PROPOSAL_SENT and lead.quote_requested_at is not None
    assert Opportunity.objects(customer=lead).count() == 0


@pytest.mark.django_db
def test_closed_lead_goes_to_history_and_a_new_one_starts(api_client):
    lost = Customer(name="Perdido", phone="5562900001002", funnel_entered_at=datetime.utcnow(),
                    funnel_archived_at=datetime.utcnow(), customer_state_now=domain.LOST, lost_reason="preco",
                    product="corporativo", quote_requested_at=datetime.utcnow() - timedelta(days=60)).save()
    assert mark_quote_requested(lost) == "marked"
    lost.reload()
    assert lost.stage == domain.NEW_LEAD and lost.product is None and lost.funnel_archived_at is None
    assert lost.quote_requested_at > datetime.utcnow() - timedelta(minutes=1)
    assert Opportunity.objects.get(customer=lost).stage == domain.LOST
    assert board_ids(api_client, domain.NEW_LEAD) == [str(lost.id)]


@pytest.mark.django_db
def test_stale_lead_from_before_the_reset_goes_to_history(api_client):
    old = Customer(name="Antigo", phone="5562900001003", customer_state_now=domain.PROPOSAL_SENT,
                   product="social", quoted_amount=5000).save()
    assert mark_quote_requested(old) == "entered"
    old.reload()
    assert old.stage == domain.NEW_LEAD and old.quoted_amount == 0 and old.funnel_entered_at is not None
    assert Opportunity.objects.get(customer=old).stage == domain.PROPOSAL_SENT
    assert board_ids(api_client, domain.NEW_LEAD) == [str(old.id)]


@pytest.mark.django_db
def test_partners_and_suppliers_are_not_marked():
    partner = Customer(name="Parceiro", phone="5562900001004", human_operator=True).save()
    supplier = Customer(name="Fornecedor", phone="5562900001005", contact_type="fornecedor").save()
    for customer in (partner, supplier):
        assert mark_quote_requested(customer) is None
        customer.reload()
        assert customer.quote_requested_at is None and customer.funnel_entered_at is None


@pytest.mark.django_db
def test_no_one_moves_a_card_into_pediu_orcamento(api_client):
    lead = Customer(name="Manual", phone="5562900001006", funnel_entered_at=datetime.utcnow(),
                    customer_state_now=domain.QUALIFIED).save()
    resp = api_client.post(f"/api/v1/crm/customers/{lead.id}/stage/", {"stage": domain.NEW_LEAD}, format="json")
    assert resp.status_code == 400 and "Pediu orçamento" in resp.data["detail"]


@pytest.mark.django_db
def test_old_funnel_entries_without_quote_request_stay_off_the_board(api_client):
    """Quem entrou no funil quando conversa nova bastava (antes de 28/10) continua fora do quadro."""
    Customer(name="Conversa antiga", phone="5562900001007", funnel_entered_at=datetime.utcnow()).save()
    assert api_client.get("/api/v1/crm/funnel/").data[domain.NEW_LEAD]["count"] == 0


@pytest.mark.django_db
def test_whatsapp_filter_orcamentos_ia(api_client):
    now = datetime.utcnow()
    asked = Customer(name="Pediu", phone="5562900001010", quote_requested_at=now).save()
    qualified = Customer(name="Qualificado", phone="5562900001011", ai_qualified_at=now).save()
    other = Customer(name="Financeiro", phone="5562900001012").save()
    for customer in (asked, qualified, other):
        ConversationModel(customer=customer, tag="AGENTE").save()

    results = api_client.get(CONVERSATIONS, {"ai_quotes": "true"}).data["results"]
    assert sorted(c["customer_name"] for c in results) == ["Pediu", "Qualificado"]
    by_name = {c["customer_name"]: c for c in results}
    assert by_name["Pediu"]["customer_quote_requested_at"] is not None
    assert by_name["Qualificado"]["customer_quote_requested_at"] is None


@pytest.mark.django_db
def test_backfill_command_dry_run_then_apply(api_client):
    since = datetime.utcnow() - timedelta(days=3)
    clicked_at = datetime.utcnow() - timedelta(days=1)

    def clicked(name, phone, button="1", **fields):
        customer = Customer(name=name, phone=phone, **fields).save()
        conversation = ConversationModel(customer=customer, tag="AGENTE").save()
        payload = {"buttonsResponseMessage": {"buttonId": button, "message": "x"}}
        MessageModel(conversation=conversation, customer=customer, role="user", direction="INCOMING",
                     content=f"<kwargs>{payload}</kwargs>", raw_metadata=payload, created_at=clicked_at).save()
        return customer

    new = clicked("Sumiu no meio", "5562900001020")
    closed = clicked("Perdido", "5562900001021", funnel_entered_at=since, customer_state_now=domain.LOST)
    clicked("Financeiro", "5562900001022", button="2")
    clicked("Botão 10", "5562900001023", button="10")

    out = StringIO()
    call_command("backfill_quote_requests", "--since", since.strftime("%Y-%m-%d"), stdout=out)
    assert "Entrariam no funil em \"Pediu orçamento\": 1" in out.getvalue() and "Sumiu no meio" in out.getvalue()
    assert "Nada gravado" in out.getvalue()
    new.reload()
    assert new.quote_requested_at is None and new.funnel_entered_at is None

    out = StringIO()
    call_command("backfill_quote_requests", "--since", since.strftime("%Y-%m-%d"), "--apply", stdout=out)
    assert "Entraram no funil em \"Pediu orçamento\": 1" in out.getvalue()
    assert "lead encerrado ou de antes do funil zerado: 1" in out.getvalue()
    new.reload()
    closed.reload()
    assert abs((new.quote_requested_at - clicked_at).total_seconds()) < 1 and new.funnel_entered_at is not None
    assert closed.quote_requested_at is None and closed.stage == domain.LOST
    assert board_ids(api_client, domain.NEW_LEAD) == [str(new.id)]
