"""Aba WhatsApp (P1): retomar IA com registro de quem retomou, atribuição, nota interna, ligação
e respostas rápidas. Mensagens internas nunca vão para o cliente nem para a IA."""
import pytest

from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from chat.repositories.message_repository import MessageRepository
from crm.models.custumer_model import Customer
from crm.models.log_service_model import ServiceLog


@pytest.fixture
def conversation():
    customer = Customer(name="Marina Souza", phone="5562991234567", product="corporativo").save()
    conv = ConversationModel(customer=customer, tag="OPERADOR", ai_active=False, needs_attention=True).save()
    MessageModel(conversation=conv, customer=customer, role="user", direction="INCOMING", content="Bom dia").save()
    return conv


def url(conv, action=""):
    return f"/api/v1/chat/conversations/{conv.id}/{action}"


def internal(conv):
    return list(MessageModel.objects(conversation=conv, direction="INTERNAL").order_by("created_at"))


@pytest.mark.django_db
def test_resume_ai_records_who_and_stays_out_of_ai_context(api_client, conversation, zapi_outbox):
    resp = api_client.post(url(conversation, "mode/"), {"mode": "AGENTE"}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["tag"] == "AGENTE" and resp.data["ai_active"] is True
    assert resp.data["handover_by_name"] == "erica" and resp.data["handover_at"]
    conversation.reload()
    assert conversation.needs_attention is False

    event = internal(conversation)[0]
    assert event.message_type == "event" and event.content.startswith("IA retomada por erica")
    assert event.hidden_from_ai
    assert ServiceLog.objects.get(action_type="HANDOVER").operator_id
    # Contexto da IA e mensagens enviadas ao cliente continuam iguais
    assert [m.content for m in MessageRepository.get_recent_context(str(conversation.id))] == ["Bom dia"]
    assert zapi_outbox == []


@pytest.mark.django_db
def test_list_toggle_patch_also_records_handover(api_client, conversation):
    conversation.update(tag="AGENTE", ai_active=True)
    resp = api_client.patch(url(conversation), {"tag": "OPERADOR"}, format="json")
    assert resp.status_code == 200
    assert resp.data["tag"] == "OPERADOR" and resp.data["ai_active"] is False
    assert internal(conversation)[0].content.startswith("Atendimento assumido por erica")


@pytest.mark.django_db
def test_partner_conversation_cannot_resume_ai(api_client, conversation):
    conversation.customer.update(human_operator=True)
    resp = api_client.post(url(conversation, "mode/"), {"mode": "AGENTE"}, format="json")
    assert resp.status_code == 400
    conversation.reload()
    assert conversation.tag == "OPERADOR"


@pytest.mark.django_db
def test_assign_conversation_and_filter_list(api_client, conversation):
    resp = api_client.post(url(conversation, "assign/"), {"assignee": "lucia"}, format="json")
    assert resp.status_code == 200 and resp.data["assignee"] == "lucia"
    assert internal(conversation)[0].content == "Conversa atribuída a Lúcia por erica."
    assert api_client.post(url(conversation, "assign/"), {"assignee": "joao"}, format="json").status_code == 400

    other = ConversationModel(customer=Customer(name="Outro", phone="5562990000001").save()).save()
    ids = [c["id"] for c in api_client.get("/api/v1/chat/conversations/", {"assignee": "lucia"}).data["results"]]
    assert ids == [str(conversation.id)]
    ids = [c["id"] for c in api_client.get("/api/v1/chat/conversations/", {"assignee": "none"}).data["results"]]
    assert ids == [str(other.id)]


@pytest.mark.django_db
def test_internal_note_goes_to_chat_and_card_timeline(api_client, conversation, zapi_outbox):
    resp = api_client.post(url(conversation, "notes/"), {"text": "Cliente prefere contato à tarde."}, format="json")
    assert resp.status_code == 201, resp.data
    note = internal(conversation)[0]
    assert note.message_type == "note" and note.role == "note" and note.hidden_from_ai
    assert ServiceLog.objects.get(action_type="NOTE_ADDED").description == "Cliente prefere contato à tarde."
    assert zapi_outbox == []
    # Aparece na lista de mensagens do painel
    contents = [m["content"] for m in api_client.get("/api/v1/chat/messages/", {"conversation": str(conversation.id)}).data["results"]]
    assert "Cliente prefere contato à tarde." in contents
    assert api_client.post(url(conversation, "notes/"), {"text": "  "}, format="json").status_code == 400


@pytest.mark.django_db
def test_call_button_logs_call_in_timeline_and_chat(api_client, conversation):
    resp = api_client.post(url(conversation, "calls/"), {"outcome": "nao_atendeu"}, format="json")
    assert resp.status_code == 201, resp.data
    assert ServiceLog.objects.get(action_type="CALL_LOGGED").metadata["outcome"] == "nao_atendeu"
    assert internal(conversation)[0].content == "Ligação registrada por erica: Não atendeu."
    assert api_client.post(url(conversation, "calls/"), {"outcome": "x"}, format="json").status_code == 400


@pytest.mark.django_db
def test_quick_replies_by_product_are_formal_and_editable(api_client):
    replies = api_client.get("/api/v1/crm/settings/").data["quick_replies"]
    products = {r["product"] for r in replies}
    assert {"geral", "estrutura_porta", "corporativo", "social", "produto_unico"} <= products
    assert not any(ord(ch) > 0x2000 for r in replies for ch in r["text"])  # sem emoji (regra 5)

    custom = [{"product": "geral", "title": "Teste", "text": "Olá, {nome}."}]
    assert api_client.patch("/api/v1/crm/settings/", {"quick_replies": custom}, format="json").status_code == 200
    assert api_client.get("/api/v1/crm/settings/").data["quick_replies"] == custom
