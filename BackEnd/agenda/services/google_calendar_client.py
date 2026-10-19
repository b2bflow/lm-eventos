"""Cliente do Google Agenda (conta Contato LM, projeto Google Cloud "LM B2B Flow").

Credenciais nunca ficam no repositório:
- client secret OAuth: GOOGLE_OAUTH_CLIENT_FILE (caminho fora do repo) ou GOOGLE_OAUTH_CLIENT_JSON;
- refresh token: LmSettings.google_refresh_token (gravado pelo callback OAuth) ou GOOGLE_REFRESH_TOKEN.
"""
import json
import os
import uuid
from datetime import datetime, timezone

from crm.models.lm_settings_model import LmSettings

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_URI = "https://oauth2.googleapis.com/token"


class GoogleNotConfigured(Exception):
    """Integração sem client secret ou sem autorização da conta."""


def _client_config() -> dict:
    raw = os.getenv("GOOGLE_OAUTH_CLIENT_JSON", "").strip()
    path = os.getenv("GOOGLE_OAUTH_CLIENT_FILE", "").strip()
    if raw:
        return json.loads(raw)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    raise GoogleNotConfigured("Client secret do Google não configurado (GOOGLE_OAUTH_CLIENT_FILE ou GOOGLE_OAUTH_CLIENT_JSON).")


def _client_section(config: dict) -> dict:
    return config.get("web") or config.get("installed") or {}


def redirect_uri() -> str:
    return os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/api/v1/agenda/google/callback/")


def calendar_id() -> str:
    return LmSettings.get().google_calendar_id or os.getenv("GOOGLE_CALENDAR_ID", "primary")


def refresh_token() -> str:
    return LmSettings.get().google_refresh_token or os.getenv("GOOGLE_REFRESH_TOKEN", "")


def is_configured() -> bool:
    try:
        _client_config()
    except GoogleNotConfigured:
        return False
    return bool(refresh_token())


def _rfc3339(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def parse_google_datetime(value: dict) -> datetime:
    """{dateTime|date} do Google -> datetime UTC sem fuso."""
    if value.get("dateTime"):
        parsed = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return datetime.fromisoformat(value["date"])


class GoogleCalendarClient:
    def __init__(self, service=None):
        self._service = service

    # --- OAuth ---------------------------------------------------------------------------

    def authorization_url(self, state: str) -> str:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=redirect_uri(), state=state)
        url, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
        return url

    def exchange_code(self, code: str, state: str) -> str:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=redirect_uri(), state=state)
        flow.fetch_token(code=code)
        token = flow.credentials.refresh_token
        if not token:
            raise GoogleNotConfigured("O Google não devolveu refresh token. Remova o acesso e autorize de novo.")
        return token

    # --- API -----------------------------------------------------------------------------

    @property
    def service(self):
        if self._service is None:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            token = refresh_token()
            if not token:
                raise GoogleNotConfigured("Conta do Google Agenda não autorizada.")
            section = _client_section(_client_config())
            # Sem `scopes`: o refresh herda os escopos concedidos na autorização. Pedir escopos aqui
            # faria um token gerado fora da plataforma (serviço OAuth da b2bflow) falhar com invalid_scope.
            # O token só funciona com o mesmo client (client_id/secret) que o emitiu.
            credentials = Credentials(
                None, refresh_token=token, token_uri=section.get("token_uri", TOKEN_URI),
                client_id=section.get("client_id"), client_secret=section.get("client_secret"),
            )
            self._service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
        return self._service

    def create_event(self, title: str, start: datetime, end: datetime, description: str = "", location: str = "",
                     with_meet: bool = False, attendees: list[str] | None = None) -> dict:
        body = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"dateTime": _rfc3339(start), "timeZone": "America/Sao_Paulo"},
            "end": {"dateTime": _rfc3339(end), "timeZone": "America/Sao_Paulo"},
        }
        if attendees:
            body["attendees"] = [{"email": email} for email in attendees]
        if with_meet:
            body["conferenceData"] = {
                "createRequest": {"requestId": uuid.uuid4().hex, "conferenceSolutionKey": {"type": "hangoutsMeet"}}
            }
        return self.service.events().insert(
            calendarId=calendar_id(), body=body, conferenceDataVersion=1 if with_meet else 0,
        ).execute()

    def calendar_info(self) -> dict:
        """Resumo da agenda conectada (nome e fuso), para conferir a conta autorizada."""
        data = self.service.calendars().get(calendarId=calendar_id()).execute()
        return {"id": data.get("id"), "summary": data.get("summary"), "time_zone": data.get("timeZone")}

    def delete_event(self, google_event_id: str) -> None:
        self.service.events().delete(calendarId=calendar_id(), eventId=google_event_id).execute()

    def list_events(self, time_min: datetime | None = None, sync_token: str | None = None) -> tuple[list[dict], str | None]:
        """Leitura incremental (syncToken). Sem token: tudo a partir de time_min. Devolve (eventos, novo token)."""
        events, page_token, next_sync = [], None, None
        while True:
            params = {"calendarId": calendar_id(), "singleEvents": True, "showDeleted": True, "maxResults": 250}
            if sync_token:
                params["syncToken"] = sync_token
            elif time_min:
                params["timeMin"] = _rfc3339(time_min)
            if page_token:
                params["pageToken"] = page_token
            response = self.service.events().list(**params).execute()
            events.extend(response.get("items", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                next_sync = response.get("nextSyncToken")
                break
        return events, next_sync
