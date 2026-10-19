"""Conferência da integração com o Google Agenda (token gerado pelo serviço OAuth da b2bflow)."""
import json
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
