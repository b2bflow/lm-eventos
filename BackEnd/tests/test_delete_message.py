"""Apagar para todos, pelo painel, mensagem enviada no WhatsApp (DELETE /chat/messages/<id>/)."""
from datetime import datetime, timedelta

import pytest
import requests

from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from chat.repositories.message_repository import MessageRepository
from crm.models.custumer_model import Customer


@pytest.fixture
def conversation():
    customer = Customer(name="Marina Souza", phone="5562991234567").save()
    return ConversationModel(customer=customer, tag="OPERADOR", ai_active=False).save()


def outgoing(conv, content="Segue a proposta", **kw):
    return MessageModel(conversation=conv, customer=conv.customer, role="OPERATOR", direction="OUTGOING",
                        content=content, **kw).save()


def url(message):
    return f"/api/v1/chat/messages/{message.id}/"


def test_send_listener_stores_every_zapi_id(conversation, monkeypatch):
    from gateway.adapters.zapi_adapter import ZAPIClient
    from gateway.listeners import handle_send_outgoing_message

    def fake_send(self, phone, message, split=True):
        self.last_sent_ids = ["ID-1", "ID-2"]
        return True

    monkeypatch.setattr(ZAPIClient, "send_message", fake_send)
    message = outgoing(conversation, "Bom dia. Tudo bem?")
    handle_send_outgoing_message({"phone": "5562991234567", "content": message.content,
                                  "message_id": str(message.id)})
    message.reload()
    assert message.raw_metadata["zapi_message_ids"] == ["ID-1", "ID-2"]
    assert message.external_id == "ID-1" and message.status == "SENT_TO_GATEWAY"


def test_operator_message_publishes_its_id(conversation, monkeypatch):
    published = []
    from events.bus import EventBus
    monkeypatch.setattr(EventBus, "publish", classmethod(lambda cls, name, payload: published.append(payload)))
    from chat.container import ChatContainer
    message = ChatContainer.get_message_service().execute_operator_message(str(conversation.id), "Oi", "1")
    assert published[0]["message_id"] == str(message.id)


@pytest.mark.django_db
def test_delete_removes_every_part_and_keeps_history(api_client, conversation, zapi_outbox):
    message = outgoing(conversation, raw_metadata={"zapi_message_ids": ["ID-1", "ID-2"]})
    conversation.update(last_message_content=message.content)

    listed = api_client.get(f"/api/v1/chat/messages/?conversation={conversation.id}").data["results"]
    assert listed[0]["deletable"] is True and listed[0]["deleted"] is False

    resp = api_client.delete(url(message))
    assert resp.status_code == 200, resp.data
    assert resp.data["deleted"] is True and resp.data["deletable"] is False
    assert [m["deleted"] for m in zapi_outbox] == ["ID-1", "ID-2"]
    assert zapi_outbox[0]["phone"] == "5562991234567"

    message.reload()
    assert message.raw_metadata["deleted_at"] and message.raw_metadata["deleted_by"]
    assert message.content == "Segue a proposta"  # histórico da equipe
    assert MessageRepository.get_recent_context(str(conversation.id)) == []  # fora da IA
    conversation.reload()
    assert conversation.last_message_content == "Mensagem apagada"

    assert api_client.delete(url(message)).status_code == 400  # já apagada


@pytest.mark.django_db
def test_file_and_phone_sent_messages_use_external_id(api_client, conversation, zapi_outbox):
    message = outgoing(conversation, external_id="FILE-1", message_type="file")
    assert api_client.delete(url(message)).status_code == 200
    assert zapi_outbox == [{"phone": "5562991234567", "deleted": "FILE-1"}]


@pytest.mark.django_db
def test_cannot_delete_incoming_old_or_without_id(api_client, conversation, zapi_outbox):
    incoming = MessageModel(conversation=conversation, customer=conversation.customer, role="user",
                            direction="INCOMING", content="Oi", external_id="IN-1").save()
    no_id = outgoing(conversation)
    old = outgoing(conversation, external_id="OLD-1", created_at=datetime.utcnow() - timedelta(days=3))

    for message in (incoming, no_id, old):
        resp = api_client.delete(url(message))
        assert resp.status_code == 400, resp.data
    assert zapi_outbox == []
    assert api_client.delete("/api/v1/chat/messages/x/").status_code == 404
    assert api_client.delete("/api/v1/chat/messages/0123456789abcdef01234567/").status_code == 404


@pytest.mark.django_db
def test_zapi_refusal_keeps_message(api_client, conversation, monkeypatch):
    from gateway.adapters.zapi_adapter import ZAPIClient

    def refuse(self, phone, message_id):
        raise requests.HTTPError("400")

    monkeypatch.setattr(ZAPIClient, "delete_message", refuse)
    message = outgoing(conversation, external_id="ID-9")
    assert api_client.delete(url(message)).status_code == 502
    message.reload()
    assert "deleted_at" not in (message.raw_metadata or {})


# --- Respostas da IA: enviadas por ai_agents/ e gravadas depois, sem o id na mão ---------------

@pytest.fixture(autouse=True)
def clean_recent_sends():
    from gateway.adapters import zapi_adapter
    zapi_adapter._RECENT_SENDS.clear()
    yield
    zapi_adapter._RECENT_SENDS.clear()


def save_ai_reply(conv, content):
    """Como generate_response_service: envia pela Z-API e depois grava como assistant."""
    from chat.container import ChatContainer
    return ChatContainer.get_message_service()._save_and_notify(
        conversation_id=str(conv.id), content=content, direction="OUTGOING", sender_role="assistant")


def test_real_send_message_remembers_every_part(monkeypatch):
    # O conftest troca send_message por um falso: carrega uma cópia do módulo com o envio de verdade.
    import importlib.util
    from gateway.adapters import zapi_adapter
    spec = importlib.util.spec_from_file_location("zapi_adapter_real", zapi_adapter.__file__)
    real = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real)

    counter = iter(range(1, 10))

    class FakeResponse:
        def __init__(self):
            self.data = {"messageId": f"PART-{next(counter)}"}

        def json(self):
            return self.data

        def raise_for_status(self):
            pass

    monkeypatch.setattr(real.requests, "post", lambda *a, **kw: FakeResponse())
    monkeypatch.setattr(real.time, "sleep", lambda s: None)
    client = real.ZAPIClient()
    text = "Oi, tudo bem? Sou o Marcelo. Posso te ajudar"
    assert client.send_message("5562991234567", text)
    ids, phone = real.ZAPIClient.claim_recent_sent(["5562991234567"], text)
    assert ids == client.last_sent_ids and len(ids) >= 2 and phone == "5562991234567"
    assert real.ZAPIClient.claim_recent_sent(["5562991234567"], text) is None  # uma vez só


@pytest.mark.django_db
def test_ai_reply_gets_ids_and_can_be_deleted(api_client, conversation, zapi_outbox):
    from gateway.adapters.zapi_adapter import ZAPIClient
    ZAPIClient.remember_sent("5562991234567", "Olá! Tudo bem? Veja o espaço", ["AI-1", "AI-2"])
    message = save_ai_reply(conversation, "Olá! Tudo bem? Veja o espaço [aqui](https://cepsbrasil.com.br/x)")
    assert message.raw_metadata["zapi_message_ids"] == ["AI-1", "AI-2"]
    assert message.external_id == "AI-1" and message.status == "SENT_TO_GATEWAY"

    listed = api_client.get(f"/api/v1/chat/messages/?conversation={conversation.id}").data["results"]
    assert listed[-1]["deletable"] is True

    assert api_client.delete(url(message)).status_code == 200
    assert [m["deleted"] for m in zapi_outbox] == ["AI-1", "AI-2"]
    assert MessageRepository.get_recent_context(str(conversation.id)) == []


@pytest.mark.django_db
def test_ai_reply_does_not_take_ids_of_other_sends(conversation):
    from chat.container import ChatContainer
    from gateway.adapters.zapi_adapter import ZAPIClient
    # Aviso enviado ao cliente sem gravar na conversa (agenda, por exemplo)
    ZAPIClient.remember_sent("5562991234567", "Lembrete: reunião amanhã às 10h", ["N-1"])
    assert not save_ai_reply(conversation, "Oi! Como posso ajudar?").raw_metadata.get("zapi_message_ids")
    # Operador pelo painel: gravado antes do envio, o id vem pelo listener
    operator = ChatContainer.get_message_service()._save_and_notify(
        conversation_id=str(conversation.id), content="Lembrete: reunião amanhã às 10h", direction="OUTGOING",
        sender_role="OPERATOR")
    assert not (operator.raw_metadata or {}).get("zapi_message_ids")
    # Passou do prazo: a gravação não pega mais o id
    from gateway.adapters import zapi_adapter
    key = ZAPIClient._recent_key("5562991234567")
    at, text, ids, phone = zapi_adapter._RECENT_SENDS[key]
    zapi_adapter._RECENT_SENDS[key] = (at - 60, text, ids, phone)
    assert not save_ai_reply(conversation, "Lembrete: reunião amanhã às 10h").raw_metadata.get("zapi_message_ids")


@pytest.mark.django_db
def test_ai_reply_sent_to_lid_is_deleted_on_the_lid(api_client, conversation, zapi_outbox):
    from gateway.adapters.zapi_adapter import ZAPIClient
    conversation.customer.update(whatsapp_lid="123456789012345@lid")
    ZAPIClient.remember_sent("123456789012345@lid", "Bom dia", ["LID-1"])
    message = save_ai_reply(conversation, "Bom dia")
    assert message.raw_metadata["zapi_phone"] == "123456789012345@lid"
    assert api_client.delete(url(message)).status_code == 200
    assert zapi_outbox == [{"phone": "123456789012345@lid", "deleted": "LID-1"}]
