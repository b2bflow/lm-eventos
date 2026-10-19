import pytest
from unittest.mock import patch
from rest_framework.test import APIClient

URL = "/api/v1/gateway/webhook/zapi/"
TOKEN = "test-webhook-token"


def text_payload(phone="5562999990000", text="Oi, quero um orçamento", message_id=None):
    payload = {
        "phone": phone, "isGroup": False, "status": "RECEIVED", "senderName": "Cliente",
        "text": {"message": text},
    }
    if message_id:
        payload["messageId"] = message_id
    return payload


@pytest.fixture
def published():
    with patch("gateway.controllers.fake_webhook.EventBus.publish_sync") as pub:
        yield pub


@pytest.mark.django_db
def test_webhook_rejects_missing_or_wrong_token(published):
    client = APIClient()
    assert client.post(URL, text_payload(), format="json").status_code == 401
    assert client.post(URL + "?token=errado", text_payload(), format="json").status_code == 401
    published.assert_not_called()


@pytest.mark.django_db
def test_webhook_accepts_token_in_query_or_header(published):
    client = APIClient()
    assert client.post(URL + f"?token={TOKEN}", text_payload(text="a"), format="json").status_code == 200
    resp = client.post(URL, text_payload(text="b"), format="json", HTTP_X_WEBHOOK_TOKEN=TOKEN)
    assert resp.status_code == 200
    assert published.call_count == 2


@pytest.mark.django_db
def test_webhook_is_open_when_no_token_configured(published, monkeypatch):
    monkeypatch.setenv("ZAPI_WEBHOOK_TOKEN", "")
    client = APIClient()
    assert client.post(URL, text_payload(), format="json").status_code == 200
    assert client.post(URL + "?token=qualquer", text_payload(text="outra"), format="json").status_code == 200


@pytest.mark.django_db
def test_same_text_same_phone_within_window_is_ignored(published):
    client = APIClient()
    first = client.post(URL + f"?token={TOKEN}", text_payload(), format="json")
    second = client.post(URL + f"?token={TOKEN}", text_payload(), format="json")
    other_phone = client.post(URL + f"?token={TOKEN}", text_payload(phone="5562988887777"), format="json")
    assert first.data["status"] == "received"
    assert second.data["status"] == "duplicate"
    assert other_phone.data["status"] == "received"
    assert published.call_count == 2


@pytest.mark.django_db
def test_redelivery_with_same_message_id_is_ignored(published):
    client = APIClient()
    client.post(URL + f"?token={TOKEN}", text_payload(text="x", message_id="ABC"), format="json")
    resp = client.post(URL + f"?token={TOKEN}", text_payload(text="y", message_id="ABC"), format="json")
    assert resp.data["status"] == "duplicate"


@pytest.mark.django_db
def test_webhook_is_not_throttled(published):
    client = APIClient()
    for i in range(15):
        resp = client.post(URL + f"?token={TOKEN}", text_payload(text=f"msg {i}"), format="json")
        assert resp.status_code == 200
