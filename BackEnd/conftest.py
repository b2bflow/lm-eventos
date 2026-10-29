import pytest
from mongoengine.connection import get_db

# Importado antes de qualquer freeze_time: o throttle guarda `timer = time.time` na classe e, se o
# módulo carregar com o relógio congelado, fica com a função falsa para sempre (TypeError no login).
import rest_framework.throttling  # noqa: E402,F401


@pytest.fixture(autouse=True)
def clean_mongo():
    """Cada teste começa com o Mongo (mongomock) vazio."""
    db = get_db()
    for name in db.list_collection_names():
        db.drop_collection(name)
    yield


@pytest.fixture(autouse=True)
def no_external_side_effects(monkeypatch):
    """Nenhum teste fala com Z-API, Redis/Socket.IO ou OpenAI de verdade."""
    sent = []

    def fake_send_message(self, phone, message):
        sent.append({"phone": phone, "message": message})
        return True

    def fake_send_buttons(self, phone, message, buttons):
        sent.append({"phone": phone, "message": message, "buttons": buttons})
        return {}

    from gateway.adapters.zapi_adapter import ZAPIClient
    from chat.gateways.adapters.socket_adapter import SocketAdapter

    monkeypatch.setattr(ZAPIClient, "send_message", fake_send_message)
    monkeypatch.setattr(ZAPIClient, "send_message_with_button", fake_send_buttons)
    monkeypatch.setattr(ZAPIClient, "send_contact", lambda self, **kw: sent.append(kw) or {})

    def fake_send_document(self, phone, document, file_name, caption="", extension="pdf"):
        sent.append({"phone": phone, "document": document, "file_name": file_name, "caption": caption})
        return {"zaapId": "fake", "messageId": "fake-doc"}

    monkeypatch.setattr(ZAPIClient, "send_document", fake_send_document)
    monkeypatch.setattr(SocketAdapter, "emit_new_message", lambda self, payload: None)
    monkeypatch.setattr(SocketAdapter, "emit_message_updated", lambda self, payload: None)
    monkeypatch.setattr(ZAPIClient, "delete_message",
                        lambda self, phone, message_id: sent.append({"phone": phone, "deleted": message_id}))
    return sent


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Redis em memória para deduplicação do webhook e demais usos."""
    import fakeredis
    import redis

    server = fakeredis.FakeServer()
    monkeypatch.setattr(redis.Redis, "from_url", classmethod(lambda cls, *a, **kw: fakeredis.FakeRedis(server=server)))
    from gateway.controllers.fake_webhook import FakeWebhookController
    FakeWebhookController.guard._redis = None
    yield
    FakeWebhookController.guard._redis = None


@pytest.fixture
def zapi_outbox(no_external_side_effects):
    return no_external_side_effects


@pytest.fixture
def admin_user(db):
    from users.models.user_model import User
    return User.objects.create_user(username="erica", email="erica@lm.test", password="x", is_staff=True)


@pytest.fixture
def api_client(admin_user):
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


def _client_for(user):
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def sdr_user(db):
    from users.models.user_model import User
    return User.objects.create_user(username="sdr_base", password="x", role="sdr")


@pytest.fixture
def sdr_api(sdr_user):
    """Cliente autenticado como SDR (sem is_staff)."""
    return _client_for(sdr_user)


@pytest.fixture
def porta_api(db):
    """Cliente autenticado como a Lúcia (papel porta)."""
    from users.models.user_model import User
    return _client_for(User.objects.create_user(username="lucia_base", password="x", role="porta"))


@pytest.fixture
def anon_api():
    from rest_framework.test import APIClient
    return APIClient()
