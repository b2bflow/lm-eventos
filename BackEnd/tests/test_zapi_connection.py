"""Configurações > Integrações & API: status, QR Code e desconectar o WhatsApp da LM na Z-API."""
import pytest
import requests

from gateway.service import zapi_connection_service as service_module

STATUS_URL = "/api/v1/gateway/zapi/status/"
DISCONNECT_URL = "/api/v1/gateway/zapi/disconnect/"


class FakeResponse:
    def __init__(self, body=None, status_code=200, content_type="application/json", content=b""):
        self._body = body
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.content = content

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


@pytest.fixture
def zapi_env(monkeypatch):
    monkeypatch.setenv("ZAPI_BASE_URL", "https://zapi.test")
    monkeypatch.setenv("ZAPI_INSTANCE_ID", "INST")
    monkeypatch.setenv("ZAPI_INSTANCE_TOKEN", "TOK")
    monkeypatch.setenv("ZAPI_CLIENT_TOKEN", "CLIENT")


@pytest.fixture
def fake_zapi(monkeypatch, zapi_env):
    """Z-API falsa: `routes[path]` é a resposta (ou exceção) de cada rota; `calls` guarda os GETs."""
    routes: dict = {}
    calls: list = []

    def fake_get(url, headers=None, timeout=None):
        prefix = "https://zapi.test/instances/INST/token/TOK/"
        assert url.startswith(prefix)
        assert headers.get("Client-Token") == "CLIENT"
        path = url[len(prefix):]
        calls.append(path)
        answer = routes.get(path)
        if isinstance(answer, Exception):
            raise answer
        if answer is None:
            return FakeResponse({}, status_code=404)
        return answer

    monkeypatch.setattr(service_module.requests, "get", fake_get)
    return routes, calls


@pytest.mark.django_db
def test_status_connected_shows_phone_and_name(api_client, fake_zapi):
    routes, calls = fake_zapi
    routes["status"] = FakeResponse({"connected": True, "smartphoneConnected": True, "error": None})
    routes["device"] = FakeResponse({"phone": "5511999998888", "name": "LM Eventos"})

    resp = api_client.get(STATUS_URL + "?qr=1")

    assert resp.status_code == 200
    assert resp.data["state"] == "connected"
    assert resp.data["connected"] is True
    assert resp.data["phone"] == "5511999998888"
    assert resp.data["name"] == "LM Eventos"
    assert resp.data["qr_code"] is None
    assert "qr-code/image" not in calls  # conectado não pede QR


@pytest.mark.django_db
def test_status_disconnected_without_qr_does_not_ask_for_it(api_client, fake_zapi):
    routes, calls = fake_zapi
    routes["status"] = FakeResponse({"connected": False, "error": "You are not connected."})

    resp = api_client.get(STATUS_URL)

    assert resp.data["state"] == "disconnected"
    assert resp.data["qr_code"] is None
    assert calls == ["status"]


@pytest.mark.django_db
def test_status_disconnected_with_qr_json(api_client, fake_zapi):
    routes, _ = fake_zapi
    routes["status"] = FakeResponse({"connected": False})
    routes["qr-code/image"] = FakeResponse({"value": "iVBORw0KGgo="})

    resp = api_client.get(STATUS_URL + "?qr=1")

    assert resp.data["state"] == "disconnected"
    assert resp.data["qr_code"] == "data:image/png;base64,iVBORw0KGgo="
    assert resp.data["error"] is None


@pytest.mark.django_db
def test_status_disconnected_with_qr_raw_image(api_client, fake_zapi):
    routes, _ = fake_zapi
    routes["status"] = FakeResponse({"connected": False})
    routes["qr-code/image"] = FakeResponse(content_type="image/png", content=b"\x89PNG")

    resp = api_client.get(STATUS_URL + "?qr=1")

    assert resp.data["qr_code"] == "data:image/png;base64,iVBORw=="


@pytest.mark.django_db
def test_qr_route_saying_connected_counts_as_connected(api_client, fake_zapi):
    """Escanearam entre o /status e o /qr-code: a tela já mostra conectado."""
    routes, _ = fake_zapi
    routes["status"] = FakeResponse({"connected": False})
    routes["qr-code/image"] = FakeResponse({"connected": True})
    routes["device"] = FakeResponse({"phone": "5511999998888"})

    resp = api_client.get(STATUS_URL + "?qr=1")

    assert resp.data["state"] == "connected"
    assert resp.data["phone"] == "5511999998888"


@pytest.mark.django_db
def test_qr_challenge_and_failure_explain(api_client, fake_zapi):
    routes, _ = fake_zapi
    routes["status"] = FakeResponse({"connected": False})
    routes["qr-code/image"] = FakeResponse({"challenge": {"type": "code"}})
    assert "verificação extra" in api_client.get(STATUS_URL + "?qr=1").data["error"]

    routes["qr-code/image"] = requests.ConnectionError("boom")
    data = api_client.get(STATUS_URL + "?qr=1").data
    assert data["state"] == "disconnected"
    assert data["qr_code"] is None
    assert "QR Code" in data["error"]


@pytest.mark.django_db
def test_status_unreachable(api_client, fake_zapi):
    routes, _ = fake_zapi
    routes["status"] = requests.Timeout("lento")

    data = api_client.get(STATUS_URL + "?qr=1").data

    assert data["state"] == "unreachable"
    assert data["connected"] is False
    assert data["error"]


@pytest.mark.django_db
def test_status_not_configured(api_client, monkeypatch):
    monkeypatch.delenv("ZAPI_INSTANCE_ID", raising=False)
    monkeypatch.setattr(service_module.requests, "get",
                        lambda *a, **kw: pytest.fail("não devia chamar a Z-API sem instância"))

    data = api_client.get(STATUS_URL).data

    assert data["state"] == "not_configured"
    assert "ZAPI_INSTANCE_ID" in data["error"]


@pytest.mark.django_db
def test_disconnect_calls_zapi_and_returns_new_status(api_client, fake_zapi):
    routes, calls = fake_zapi
    routes["disconnect"] = FakeResponse({"value": True})
    routes["status"] = FakeResponse({"connected": False})

    resp = api_client.post(DISCONNECT_URL)

    assert resp.status_code == 200
    assert resp.data["state"] == "disconnected"
    assert calls[0] == "disconnect"


@pytest.mark.django_db
def test_disconnect_failure_is_502(api_client, fake_zapi):
    routes, _ = fake_zapi
    routes["disconnect"] = requests.ConnectionError("fora do ar")
    resp = api_client.post(DISCONNECT_URL)
    assert resp.status_code == 502
    assert "desconectar" in resp.data["detail"]

    routes["disconnect"] = FakeResponse({"value": False})
    assert api_client.post(DISCONNECT_URL).status_code == 502


@pytest.mark.django_db
def test_only_admin(sdr_api, anon_api, fake_zapi):
    routes, calls = fake_zapi
    routes["disconnect"] = FakeResponse({"value": True})

    assert sdr_api.get(STATUS_URL).status_code == 403
    assert sdr_api.post(DISCONNECT_URL).status_code == 403
    assert anon_api.get(STATUS_URL).status_code in (401, 403)
    assert anon_api.post(DISCONNECT_URL).status_code in (401, 403)
    assert calls == []
