"""Id malformado na URL ou na query volta 400/404 em vez de derrubar a consulta no Mongo com 500."""
import pytest

from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from crm.models.custumer_model import Customer

MISSING = "0123456789abcdef01234567"


@pytest.mark.django_db
@pytest.mark.parametrize("url", [
    "/api/v1/chat/messages/?conversation=x",
    "/api/v1/chat/messages/?customer=x",
    "/api/v1/sales/proposals/?customer=x",
    "/api/v1/crm/customers/x/tasks/",
    "/api/v1/crm/customers/x/timeline/",
])
def test_malformed_ids_on_get_are_bad_requests(api_client, url):
    resp = api_client.get(url)
    assert resp.status_code == 400, resp.data


@pytest.mark.django_db
def test_card_action_with_malformed_id_is_bad_request(api_client):
    resp = api_client.post("/api/v1/crm/customers/x/stage/", {"stage": "QUALIFIED"}, format="json")
    assert resp.status_code == 400 and resp.data["detail"] == "Lead não encontrado."


@pytest.mark.django_db
def test_operator_message_to_malformed_conversation_is_not_found(api_client):
    resp = api_client.post("/api/v1/chat/messages/", {"conversation_id": "x", "content": "Oi"}, format="json")
    assert resp.status_code == 404 and resp.data["detail"] == "Conversa não encontrada."


@pytest.mark.django_db
def test_message_detail_returns_the_message_or_404(api_client):
    customer = Customer(name="Ana", phone="5562999990000").save()
    conversation = ConversationModel(customer=customer).save()
    message = MessageModel(conversation=conversation, customer=customer, role="user", direction="INCOMING",
                           status="RECEIVED", content="Oi").save()

    resp = api_client.get(f"/api/v1/chat/messages/{message.id}/")
    assert resp.status_code == 200 and resp.data["content"] == "Oi"
    assert api_client.get(f"/api/v1/chat/messages/{MISSING}/").status_code == 404
    assert api_client.get("/api/v1/chat/messages/x/").status_code == 404
