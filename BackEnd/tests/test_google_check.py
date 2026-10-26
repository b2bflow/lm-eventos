"""Conferência da integração com o Google Agenda (token gerado pelo serviço OAuth da b2bflow)."""
import base64
import json
from datetime import datetime
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

CLIENT = {"web": {"client_id": "123-abc.apps.googleusercontent.com", "client_secret": "s",
                  "token_uri": "https://oauth2.googleapis.com/token"}}


@pytest.fixture
def google_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_JSON", json.dumps(CLIENT))
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "1//refresh-fake")


def fake_service():
    service = MagicMock()
    service.calendars().get().execute.return_value = {"id": "contato@lm.test", "summary": "Contato LM", "timeZone": "America/Sao_Paulo"}
    service.events().list().execute.return_value = {"items": [
        {"id": "e1", "status": "confirmed", "summary": "Reunião", "start": {"dateTime": "2026-10-20T10:00:00-03:00"}}
    ], "nextSyncToken": "t"}
    service.events().insert().execute.return_value = {"id": "tmp", "hangoutLink": "https://meet.google.com/x"}
    return service


@pytest.mark.django_db
def test_credentials_do_not_force_scopes(google_env):
    from agenda.services.google_calendar_client import GoogleCalendarClient
    with patch("google.oauth2.credentials.Credentials") as creds, patch("googleapiclient.discovery.build") as build:
        GoogleCalendarClient().service  # noqa: B018
    kwargs = creds.call_args.kwargs
    assert kwargs["refresh_token"] == "1//refresh-fake" and kwargs["client_id"].startswith("123-abc")
    assert "scopes" not in kwargs
    build.assert_called_once()


@pytest.mark.django_db
def test_check_command_reads_and_writes_without_printing_token(google_env):
    out = StringIO()
    with patch("agenda.services.google_calendar_client.GoogleCalendarClient.service", new=fake_service()):
        call_command("check_google_calendar", "--create-test", stdout=out)
    text = out.getvalue()
    assert "Conectado à agenda: Contato LM" in text
    assert "Próximos eventos lidos: 1" in text
    assert "Escrita OK" in text
    assert "refresh-fake" not in text


@pytest.mark.django_db
def test_check_command_explains_missing_token(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_JSON", json.dumps(CLIENT))
    monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)
    with pytest.raises(CommandError, match="GOOGLE_REFRESH_TOKEN"):
        call_command("check_google_calendar", stdout=StringIO())


@pytest.mark.django_db
def test_env_token_marks_agenda_connected(google_env, api_client):
    status = api_client.get("/api/v1/agenda/google/status/").data
    assert status == {**status, "client_configured": True, "authorized": True, "connected": True}


@pytest.mark.django_db
def test_client_secret_accepts_base64_and_rejects_garbage(monkeypatch):
    from agenda.services.google_calendar_client import GoogleNotConfigured, _client_config
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_FILE", raising=False)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_JSON", base64.b64encode(json.dumps(CLIENT).encode()).decode())
    assert _client_config() == CLIENT
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_JSON", "nada-a-ver")
    with pytest.raises(GoogleNotConfigured, match="inválido"):
        _client_config()


class FakeCalendar:
    """Google Agenda em memória com uma agenda que já tem um compromisso da Erica."""

    def __init__(self):
        self.events = {"erica1": {"id": "erica1", "status": "confirmed", "summary": "Dentista",
                                  "start": {"dateTime": "2099-01-10T10:00:00-03:00"},
                                  "end": {"dateTime": "2099-01-10T11:00:00-03:00"}}}
        self.calls = []

    def calendar_info(self):
        return {"id": "contato@lm.test", "summary": "Contato LM", "time_zone": "America/Sao_Paulo"}

    def list_events(self, time_min=None, sync_token=None):
        return list(self.events.values()), "tok"

    @staticmethod
    def _dt(value: datetime):
        return {"dateTime": value.isoformat() + "Z"}

    def create_event(self, title, start, end, **kwargs):
        self.calls.append(("create", title))
        self.events["t1"] = {"id": "t1", "status": "confirmed", "summary": title, "start": self._dt(start), "end": self._dt(end)}
        return self.events["t1"]

    def update_event(self, google_event_id, title=None, start=None, end=None, **kwargs):
        self.calls.append(("update", google_event_id))
        event = self.events[google_event_id]
        event.update({k: v for k, v in {"summary": title, "start": start and self._dt(start),
                                         "end": end and self._dt(end)}.items() if v})
        return event

    def get_event(self, google_event_id):
        return self.events[google_event_id]

    def delete_event(self, google_event_id):
        self.calls.append(("delete", google_event_id))
        self.events[google_event_id]["status"] = "cancelled"


@pytest.mark.django_db
def test_roundtrip_only_touches_its_own_test_event(google_env):
    from agenda.models import CalendarEvent
    fake = FakeCalendar()
    out = StringIO()
    with patch("agenda.management.commands.check_google_calendar.GoogleCalendarClient", return_value=fake):
        call_command("check_google_calendar", "--roundtrip", stdout=out)
    text = out.getvalue()
    assert "Ida e volta OK" in text, text
    assert fake.calls == [("create", "TESTE integração LM (pode apagar)"), ("update", "t1"), ("delete", "t1")]
    assert fake.events["erica1"]["summary"] == "Dentista" and fake.events["erica1"]["status"] == "confirmed"
    # O compromisso da Erica fica espelhado; o evento de teste não deixa rastro na plataforma.
    assert CalendarEvent.objects(google_event_id="erica1").count() == 1
    assert CalendarEvent.objects(google_event_id="t1").count() == 0


@pytest.mark.django_db
def test_authorization_url_has_no_pkce_challenge(google_env, monkeypatch):
    # O verificador PKCE se perderia entre o link e o callback (requests diferentes): invalid_grant.
    from agenda.services.google_calendar_client import GoogleCalendarClient
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_JSON", json.dumps(
        {"web": {**CLIENT["web"], "auth_uri": "https://accounts.google.com/o/oauth2/auth"}}))
    url = GoogleCalendarClient().authorization_url("st", redirect="https://exemplo.test/cb")
    assert "code_challenge" not in url and "redirect_uri=https%3A%2F%2Fexemplo.test%2Fcb" in url


@pytest.mark.django_db
def test_authorize_command_saves_token_from_pasted_url_without_printing(google_env, tmp_path, monkeypatch):
    from crm.models.lm_settings_model import LmSettings
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_JSON", json.dumps(
        {"web": {**CLIENT["web"], "redirect_uris": ["https://antigo.test/auth/google/callback"]}}))
    seen = {}

    def fake_exchange(self, code, state, redirect=None):
        seen.update(code=code, redirect=redirect)
        return "1//novo-token"

    monkeypatch.setattr("agenda.services.google_calendar_client.GoogleCalendarClient.exchange_code", fake_exchange)
    env = tmp_path / ".env"
    env.write_text("OUTRA=1\nGOOGLE_REFRESH_TOKEN=velho\n", encoding="utf-8")
    out = StringIO()
    call_command("google_authorize", "--env-file", str(env), stdout=out,
                 code="https://antigo.test/auth/google/callback?state=&code=4/abc&scope=x")
    assert seen == {"code": "4/abc", "redirect": "https://antigo.test/auth/google/callback"}
    assert LmSettings.get().google_refresh_token == "1//novo-token"
    assert env.read_text(encoding="utf-8") == "OUTRA=1\nGOOGLE_REFRESH_TOKEN=1//novo-token\n"
    assert "novo-token" not in out.getvalue()


@pytest.mark.django_db
def test_registered_callback_path_saves_token(monkeypatch):
    # Endereço cadastrado no client: https://oauth.b2bflow.com.br/auth/google/callback (sem barra no fim).
    from django.core import signing
    from rest_framework.test import APIClient
    from agenda.controllers import STATE_SALT
    from crm.models.lm_settings_model import LmSettings
    monkeypatch.setenv("FRONTEND_URL", "https://painel.test")
    monkeypatch.setattr("agenda.services.google_calendar_client.GoogleCalendarClient.exchange_code",
                        lambda self, code, state, redirect=None: "1//do-callback")
    state = signing.dumps({"uid": 1}, salt=STATE_SALT)
    resp = APIClient().get("/auth/google/callback", {"state": state, "code": "4/x"})
    assert resp.status_code == 302 and resp["Location"] == "https://painel.test/agenda?google=ok"
    assert LmSettings.get().google_refresh_token == "1//do-callback"
