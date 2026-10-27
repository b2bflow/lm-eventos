"""Contatos (P1): contato com vários leads ao longo do tempo, telefone sem duplicar e importação
da lista de parceiros da Erica por CSV."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from crm.container import CrmContainer
from crm.models.custumer_model import Customer
from crm.models.log_service_model import ServiceLog
from crm.models.opportunity_model import Opportunity
from crm.models.sdr_task_model import SdrTask
from crm.phones import normalize_phone, phone_variants
from sales.models import Proposal

CONTACTS = "/api/v1/crm/contacts/"
IMPORT = "/api/v1/crm/contacts/import-partners/"


@pytest.fixture
def sdr_client(db):
    from users.models.user_model import User
    client = APIClient()
    client.force_authenticate(User.objects.create_user(username="sdr", password="x", role="sdr"))
    return client


@pytest.fixture
def lost_lead():
    """Lead de porta perdido por preço, com proposta, anexo e linha do tempo."""
    customer = Customer(name="Rafael", phone="5562988881111", product="estrutura_porta", contact_type="lead",
                        customer_state_now="LOST", lost_reason="preco", quoted_amount=4200,
                        attachments=[{"url": "https://cdn.test/lista.jpg", "kind": "lista_pecas", "name": "lista.jpg"}],
                        qualification={"data_retirada": "24/10/2026"}, created_at=datetime(2026, 9, 1)).save()
    Proposal(customer=customer, version=1, mode="porta", total=4200, status="recusada").save()
    ServiceLog(customer=customer, action_type="NOTE_ADDED", description="Achou caro.").save()
    ConversationModel(customer=customer, tag="AGENTE", ai_active=True).save()
    return customer


def test_phone_normalization_and_ninth_digit_variants():
    assert normalize_phone("(62) 99999-1111") == "5562999991111"
    assert normalize_phone("+55 62 3241-0000") == "556232410000"
    assert normalize_phone("062 99999 1111") == "5562999991111"
    assert normalize_phone("1234") is None
    assert phone_variants("5562999991111") == ["5562999991111", "556299991111"]
    assert phone_variants("556299991111") == ["556299991111", "5562999991111"]
    assert phone_variants("556232410000") == ["556232410000"]  # fixo não ganha o 9


@pytest.mark.django_db
def test_incoming_without_ninth_digit_reuses_contact():
    customer = Customer(name="Ana", phone="5562999991111").save()
    found = CrmContainer.get_customer_service().get_customer_by_phone("556299991111")
    assert found["id"] == str(customer.id)


@pytest.mark.django_db
def test_create_contact_normalizes_phone_and_rejects_duplicate(api_client):
    resp = api_client.post(CONTACTS, {"name": "Buffet Aurora", "phone": "(62) 99999-2222", "company": "Aurora",
                                      "contact_type": "lead", "origin": "indicacao"}, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["phone"] == "5562999992222"
    assert resp.data["leads"][0]["current"] is True and resp.data["leads"][0]["stage"] == "NEW_LEAD"

    dup = api_client.post(CONTACTS, {"phone": "556299992222"}, format="json")
    assert dup.status_code == 409
    assert dup.data["existing_id"] == resp.data["id"]
    assert api_client.post(CONTACTS, {"phone": "123"}, format="json").status_code == 400


@pytest.mark.django_db
def test_list_contacts_search_and_partner_filter(api_client, lost_lead):
    Customer(name="Cerimonial Lírio", phone="5562977770000", contact_type="parceiro", owner="erica",
             human_operator=True).save()
    by_phone = api_client.get(CONTACTS, {"search": "8888-1111"}).data
    assert [c["name"] for c in by_phone["results"]] == ["Rafael"]
    assert by_phone["results"][0]["leads_count"] == 1
    partners = api_client.get(CONTACTS, {"partner": "true"}).data
    assert [c["name"] for c in partners["results"]] == ["Cerimonial Lírio"]
    assert partners["results"][0]["current_lead"] is None and partners["results"][0]["leads_count"] == 0


@pytest.mark.django_db
def test_new_lead_archives_closed_lead_with_history(api_client, lost_lead):
    resp = api_client.post(f"{CONTACTS}{lost_lead.id}/new-lead/", {"product": "corporativo"}, format="json")
    assert resp.status_code == 200, resp.data
    detail = resp.data

    current, previous = detail["leads"]
    assert current["current"] and current["number"] == 2
    assert current["stage"] == "NEW_LEAD" and current["product"] == "corporativo"
    assert current["proposals"] == [] and current["attachments"] == []
    assert previous["number"] == 1 and previous["stage"] == "LOST" and previous["lost_reason"] == "preco"
    assert previous["quoted_amount"] == 4200 and previous["qualification"]["data_retirada"] == "24/10/2026"
    assert [p["total"] for p in previous["proposals"]] == [4200]
    assert detail["attachments"][0]["lead_number"] == 1

    lost_lead.reload()
    assert lost_lead.lost_reason is None and lost_lead.quoted_amount == 0 and lost_lead.qualification == {}
    # Card do funil mostra só o lead atual
    timeline = api_client.get(f"/api/v1/crm/customers/{lost_lead.id}/timeline/").data
    assert all("Achou caro" not in t["description"] for t in timeline)
    assert api_client.get(f"/api/v1/sales/proposals/?customer={lost_lead.id}").data == []
    old = api_client.get(f"{CONTACTS}{lost_lead.id}/timeline/", {"lead": previous["id"]}).data
    assert [t["description"] for t in old] == ["Achou caro."]


@pytest.mark.django_db
def test_new_lead_refused_while_current_lead_is_open(api_client, lost_lead):
    lost_lead.update(customer_state_now="PROPOSAL_SENT", proposal_sent_at=datetime.utcnow(),
                     funnel_entered_at=datetime.utcnow())
    resp = api_client.post(f"{CONTACTS}{lost_lead.id}/new-lead/", {"product": "social"}, format="json")
    assert resp.status_code == 400
    assert Opportunity.objects.count() == 0


@pytest.mark.django_db
def test_start_lead_from_ai_after_contract_signed_opens_new_lead():
    customer = Customer(name="Eva", phone="5562966660000", product="corporativo", customer_state_now="CONTRACT_SIGNED",
                        contract_value=12680, created_at=datetime.utcnow() - timedelta(days=5)).save()
    CrmContainer.get_lead_qualification_service().start_lead(str(customer.id), "social")
    customer.reload()
    assert customer.lead_number == 2 and customer.product == "social" and customer.contract_value == 0
    assert Opportunity.objects.get(customer=customer).contract_value == 12680


@pytest.mark.django_db
def test_dashboard_keeps_revenue_of_archived_lead(api_client):
    customer = Customer(name="Eva", phone="5562966660000", product="corporativo", customer_state_now="CONTRACT_SIGNED",
                        contract_value=12680, created_at=datetime.utcnow() - timedelta(days=5)).save()
    CrmContainer.get_contact_service().start_new_lead(str(customer.id), "social")
    data = api_client.get("/api/v1/analytics/dashboard/metrics/").data
    assert data["confirmed_revenue"] == 12680
    assert data["events_confirmed"] == 1 and data["total_leads"] == 2


@pytest.mark.django_db
def test_patch_contact_marks_partner_silently(api_client, lost_lead, zapi_outbox):
    lost_lead.update(customer_state_now="QUALIFIED", lost_reason=None)
    SdrTask(customer=lost_lead, type="ligar_15min", due_at=datetime.utcnow()).save()
    resp = api_client.patch(f"{CONTACTS}{lost_lead.id}/", {"human_operator": True, "company": "Eventos RF"}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["human_operator"] and resp.data["owner"] == "erica" and resp.data["company"] == "Eventos RF"
    assert SdrTask.objects.get().status == "canceled"
    conversation = ConversationModel.objects.get(customer=lost_lead)
    assert conversation.tag == "OPERADOR" and conversation.ai_active is False
    assert zapi_outbox == []  # sem aviso para a Erica (cadastro, não atendimento)


CSV = """Nome;Telefone
Cerimonial Lírio;(62) 97777-0000
Rafael;62 8888-1111
Som Parceiro;62 95555-4444
Repetido;(62) 95555-4444
Sem número;abc
"""


@pytest.mark.django_db
def test_import_partners_dry_run_then_import(api_client, lost_lead):
    Customer(name="Já parceiro", phone="5562955554444", human_operator=True, owner="erica").save()

    preview = api_client.post(IMPORT, {"content": CSV, "dry_run": True}, format="json")
    assert preview.status_code == 200, preview.data
    assert (preview.data["created"], preview.data["updated"], preview.data["unchanged"]) == (1, 1, 1)
    assert preview.data["repeated"] == 1 and preview.data["invalid"][0]["line"] == 6
    assert Customer.objects.count() == 2

    result = api_client.post(IMPORT, {"content": CSV}, format="json").data
    assert (result["created"], result["updated"], result["unchanged"]) == (1, 1, 1)
    created = Customer.objects.get(phone="5562977770000")
    assert created.name == "Cerimonial Lírio" and created.human_operator and created.owner == "erica"
    assert created.contact_type == "parceiro" and created.new_service is False
    lost_lead.reload()
    assert lost_lead.human_operator and lost_lead.contact_type == "parceiro"
    assert ConversationModel.objects.get(customer=lost_lead).tag == "OPERADOR"


@pytest.mark.django_db
def test_import_accepts_excel_latin1_file_without_header(api_client):
    content = "Cerimonial São José,62999993333\n62999994444\n".encode("latin-1")
    upload = SimpleUploadedFile("parceiros.csv", content, content_type="text/csv")
    result = api_client.post(IMPORT, {"file": upload}, format="multipart").data
    assert result["created"] == 2
    assert Customer.objects.get(phone="5562999993333").name == "Cerimonial São José"


@pytest.mark.django_db
def test_import_is_admin_or_b2bflow_only(sdr_client):
    assert sdr_client.post(IMPORT, {"content": "62999993333"}, format="json").status_code == 403


@pytest.mark.django_db
def test_partner_message_goes_to_operator_without_menu_or_ai(zapi_outbox):
    Customer(name="Cerimonial Lírio", phone="5562977770000", contact_type="parceiro", owner="erica",
             human_operator=True, new_service=False).save()
    with patch("events.tasks.trigger_ai_agent_task.apply_async") as ai_task:
        resp = APIClient().post("/api/v1/gateway/webhook/zapi/?token=test-webhook-token",
                                {"phone": "5562977770000", "isGroup": False, "status": "RECEIVED",
                                 "text": {"message": "Erica, tem gradil livre sábado?"}}, format="json")
    assert resp.status_code == 200
    conversation = ConversationModel.objects.get()
    assert conversation.tag == "OPERADOR" and conversation.needs_attention
    assert MessageModel.objects(conversation=conversation).count() == 1
    assert zapi_outbox == [] and not ai_task.called


@pytest.mark.django_db
def test_delete_contact_cascades_conversations(api_client, lost_lead):
    from agenda.models import CalendarEvent
    from inventory.models import InventoryItem, InventoryReservation

    conversation = ConversationModel.objects.get(customer=lost_lead)
    MessageModel(conversation=conversation, customer=lost_lead, role="user", direction="INCOMING", content="Oi").save()
    proposal = Proposal.objects.get(customer=lost_lead)
    item = InventoryItem(code="ilum_par", line="Iluminação", name="Refletor PAR LED", qty_total=4).save()
    start = datetime(2026, 11, 10)
    reservation = InventoryReservation(item=item, proposal_id=str(proposal.id), customer=lost_lead, qty=2,
                                       start=start, end=start + timedelta(days=1)).save()
    event = CalendarEvent(type="evento_confirmado", title="Show", customer=lost_lead, start=start,
                          end=start + timedelta(hours=5)).save()
    other = Customer(name="Outro", phone="5562900000000").save()
    ConversationModel(customer=other).save()

    resp = api_client.delete(f"{CONTACTS}{lost_lead.id}/")

    assert resp.status_code == 200 and resp.json()["conversations"] == 1
    assert Customer.objects(id=lost_lead.id).count() == 0
    assert ConversationModel.objects(customer=lost_lead.id).count() == 0
    assert MessageModel.objects(conversation=conversation.id).count() == 0
    assert Proposal.objects(customer=lost_lead.id).count() == 0
    assert ServiceLog.objects(customer=lost_lead.id).count() == 0
    assert ConversationModel.objects(customer=other).count() == 1  # os outros contatos ficam
    reservation.reload()
    assert reservation.status == "cancelado" and reservation.customer is None and reservation.client_name == "Rafael"
    event.reload()
    assert event.customer is None
    assert api_client.delete(f"{CONTACTS}{lost_lead.id}/").status_code == 404


def test_delete_contact_is_admin_only(sdr_client, lost_lead):
    assert sdr_client.delete(f"{CONTACTS}{lost_lead.id}/").status_code == 403
    assert ConversationModel.objects(customer=lost_lead).count() == 1
