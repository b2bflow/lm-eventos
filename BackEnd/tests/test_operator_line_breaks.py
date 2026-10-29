"""Mensagem digitada no painel sai para o WhatsApp como foi escrita (quebras de linha, pontos)."""
import pytest

from chat.models.conversation_model import ConversationModel
from crm.models.custumer_model import Customer
from gateway.adapters.zapi_adapter import ZAPIClient

REAL_SEND = ZAPIClient.send_message  # o conftest troca por um fake; aqui testamos o envio de verdade


class FakeResponse:
    def __init__(self, n):
        self.n = n

    def json(self):
        return {"messageId": f"ID-{self.n}"}

    def raise_for_status(self):
        pass


@pytest.fixture
def zapi_posts(monkeypatch):
    posts = []
    monkeypatch.setattr(ZAPIClient, "send_message", REAL_SEND)
    monkeypatch.setattr(ZAPIClient, "_resolve_url", lambda self: "https://zapi.test")

    def fake_post(url, json=None, headers=None, **kw):
        posts.append(dict(json))
        return FakeResponse(len(posts))

    monkeypatch.setattr("gateway.adapters.zapi_adapter.requests.post", fake_post)
    monkeypatch.setattr("gateway.adapters.zapi_adapter.time.sleep", lambda s: None)
    return posts


TEXT = "Oi, Marina!\nSegue o resumo.\n\n1. Som\n2. Iluminação. Qualquer dúvida?"


def test_split_false_sends_text_untouched(zapi_posts):
    client = ZAPIClient()
    assert client.send_message("5562991234567", TEXT, split=False)
    assert [p["message"] for p in zapi_posts] == [TEXT]
    assert client.last_sent_ids == ["ID-1"]


def test_default_still_splits_sentences(zapi_posts):
    assert ZAPIClient().send_message("5562991234567", "Bom dia. Tudo bem?")
    assert [p["message"] for p in zapi_posts] == ["Bom dia", "Tudo bem?"]


def test_operator_message_keeps_line_breaks(monkeypatch, zapi_posts):
    customer = Customer(name="Marina Souza", phone="5562991234567").save()
    conversation = ConversationModel(customer=customer, tag="OPERADOR", ai_active=False).save()
    published = []
    from events.bus import EventBus
    monkeypatch.setattr(EventBus, "publish", classmethod(lambda cls, name, payload: published.append(payload)))
    from chat.container import ChatContainer
    message = ChatContainer.get_message_service().execute_operator_message(str(conversation.id), TEXT, "1")
    assert message.content == TEXT
    assert published[0]["keep_format"] is True

    from gateway.listeners import handle_send_outgoing_message
    handle_send_outgoing_message(published[0])
    assert [p["message"] for p in zapi_posts] == [TEXT]
