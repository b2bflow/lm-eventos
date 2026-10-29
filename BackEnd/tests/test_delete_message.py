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

    def fake_send(self, phone, message):
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
