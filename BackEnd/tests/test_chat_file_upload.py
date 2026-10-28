"""Envio de arquivo pela aba WhatsApp: qualquer tipo, inclusive o PDF de proposta de ~26 MB."""
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from chat.models.chat_file_model import ChatFile
from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from crm.models.custumer_model import Customer

URL = "/api/v1/chat/messages/files/"
MB = 1024 * 1024


@pytest.fixture
def conversation():
    customer = Customer(name="Ana", phone="5562999990000").save()
    return ConversationModel(customer=customer).save()


@pytest.fixture
def zapi():
    with patch("gateway.adapters.zapi_adapter.requests.post") as post:
        post.return_value.json.return_value = {"messageId": "ABC"}
        yield post


def _upload(api_client, conversation, name, body, content_type):
    file = SimpleUploadedFile(name, body, content_type=content_type)
    return api_client.post(URL, {"conversation_id": str(conversation.id), "file": file}, format="multipart")


def _sent(zapi):
    return zapi.call_args.args[0], zapi.call_args.kwargs["json"]


@pytest.mark.django_db
def test_small_pdf_goes_inline_as_document(api_client, conversation, zapi):
    resp = _upload(api_client, conversation, "Proposta.pdf", b"%PDF-1.4\n" + b"0" * 50_000, "application/pdf")

    assert resp.status_code == 201, resp.data
    url, payload = _sent(zapi)
    assert url.endswith("/send-document/pdf")
    assert payload["fileName"] == "Proposta.pdf"
    assert payload["document"].startswith("data:application/pdf;base64,")


@pytest.mark.django_db
def test_big_pdf_goes_by_public_link_and_link_serves_the_file(api_client, conversation, zapi, monkeypatch):
    monkeypatch.setenv("BACKEND_PUBLIC_URL", "https://api.exemplo.com.br")
    body = b"%PDF-1.4\n" + b"0" * (26 * MB)
    resp = _upload(api_client, conversation, "Proposta Comercial - Corporativo (1).pdf", body, "application/pdf")

    assert resp.status_code == 201, resp.data
    url, payload = _sent(zapi)
    assert url.endswith("/send-document/pdf")
    link = payload["document"]
    assert link.startswith("https://api.exemplo.com.br/api/v1/chat/files/")

    message = MessageModel.objects.get(id=resp.data["message_id"])
    assert message.message_type == "file" and message.media_url == link

    api_client.force_authenticate(user=None)
    download = api_client.get(link.removeprefix("https://api.exemplo.com.br"))
    assert download.status_code == 200
    assert b"".join(download.streaming_content) == body
    assert download["Content-Type"] == "application/pdf"


@pytest.mark.django_db
def test_big_file_without_public_url_still_goes_inline(api_client, conversation, zapi, monkeypatch):
    monkeypatch.setenv("BACKEND_PUBLIC_URL", "http://localhost:8050")
    resp = _upload(api_client, conversation, "planta.dwg", b"x" * (11 * MB), "application/octet-stream")

    assert resp.status_code == 201, resp.data
    url, payload = _sent(zapi)
    assert url.endswith("/send-document/dwg") and payload["document"].startswith("data:")


@pytest.mark.django_db
@pytest.mark.parametrize("name, content_type, endpoint", [
    ("foto.jpg", "image/jpeg", "/send-image"),
    ("logo.svg", "image/svg+xml", "/send-document/svg"),
    ("foto.heic", "image/heic", "/send-document/heic"),
    ("audio.wav", "audio/wav", "/send-document/wav"),
    ("video.mp4", "video/mp4", "/send-video"),
    ("planilha.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "/send-document/xlsx"),
    ("arquivos.zip", "application/zip", "/send-document/zip"),
    ("LEIAME", "text/plain", "/send-document/txt"),
    ("sem-tipo", "", "/send-document/bin"),
])
def test_any_file_type_is_sent(api_client, conversation, zapi, name, content_type, endpoint):
    resp = _upload(api_client, conversation, name, b"conteudo", content_type)

    assert resp.status_code == 201, resp.data
    url, _ = _sent(zapi)
    assert url.endswith(endpoint)


@pytest.mark.django_db
def test_file_over_the_limit_is_rejected_with_the_limit(api_client, conversation, zapi, monkeypatch):
    monkeypatch.setenv("CHAT_FILE_UPLOAD_MAX_MB", "1")
    resp = _upload(api_client, conversation, "grande.pdf", b"0" * (3 * MB), "application/pdf")

    assert resp.status_code == 413 and "1MB" in resp.data["detail"]
    zapi.assert_not_called()


@pytest.mark.django_db
def test_zapi_refusal_is_a_clear_error(api_client, conversation, zapi):
    import requests
    zapi.return_value.raise_for_status.side_effect = requests.HTTPError("413")
    resp = _upload(api_client, conversation, "a.pdf", b"%PDF", "application/pdf")

    assert resp.status_code == 502 and "Z-API" in resp.data["detail"]


@pytest.mark.django_db
def test_file_link_needs_a_valid_token(api_client, conversation, zapi):
    _upload(api_client, conversation, "a.pdf", b"%PDF", "application/pdf")
    chat_file = ChatFile.objects.first()

    api_client.force_authenticate(user=None)
    assert api_client.get(f"/api/v1/chat/files/{chat_file.id}/a.pdf").status_code == 404
    assert api_client.get(f"/api/v1/chat/files/{chat_file.id}/a.pdf?t=forjado").status_code == 404


@pytest.mark.django_db
def test_html_file_link_is_sandboxed(api_client, conversation, zapi):
    _upload(api_client, conversation, "x.html", b"<script>alert(1)</script>", "text/html")
    link = MessageModel.objects.first().media_url

    api_client.force_authenticate(user=None)
    assert api_client.get(link)["Content-Security-Policy"] == "sandbox"
