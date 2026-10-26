import os
from datetime import datetime, timedelta, timezone

from django.core import signing
from django.shortcuts import redirect
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from agenda.services.agenda_service import AgendaService, ScheduleConflict
from crm.services.pipeline_service import PermissionDeniedError
from agenda.services.google_calendar_client import (
    GoogleCalendarClient, GoogleNotConfigured, is_configured, redirect_uri, refresh_token,
)
from crm.models.lm_settings_model import LmSettings
from users.permissions import has_role
from utils.logger import logger

service = AgendaService()
STATE_SALT = "lm-google-oauth"


def _parse(value: str | None, label: str) -> datetime:
    if not value:
        raise ValueError(f"Informe {label}.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


class EventsController(APIView):
    """GET /agenda/events/?start=&end= (ISO; padrão: semana atual). POST agenda a partir do card.

    POST: {type: reuniao_online|visita_tecnica|evento_confirmado|bloqueio, start, end, customer_id,
           title, location, notes, notify_customer}
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            start = _parse(request.query_params.get("start"), "o início") if request.query_params.get("start") \
                else datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
            end = _parse(request.query_params.get("end"), "o fim") if request.query_params.get("end") \
                else start + timedelta(days=7)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(service.events(start, end))

    def post(self, request):
        data = request.data
        try:
            event = service.schedule(
                data.get("type"), _parse(data.get("start"), "o início"), _parse(data.get("end"), "o fim"),
                customer_id=data.get("customer_id") or None, title=data.get("title") or None,
                location=data.get("location") or None, notes=data.get("notes") or None,
                notify_customer=data.get("notify_customer", True) not in (False, "false"), user=request.user,
                force=data.get("force") in (True, "true", "1"),
            )
        except ScheduleConflict as e:
            return Response({"detail": str(e), "conflicts": e.conflicts, "can_force": has_role(request.user)},
                            status=status.HTTP_409_CONFLICT)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(event, status=status.HTTP_201_CREATED)


class EventDetailController(APIView):
    """PATCH: {start, end, title, location, notes, notify_customer, force} (só eventos da plataforma). DELETE cancela."""
    permission_classes = [IsAuthenticated]

    def patch(self, request, event_id):
        data = request.data
        try:
            event = service.update(
                event_id,
                start=_parse(data["start"], "o início") if data.get("start") else None,
                end=_parse(data["end"], "o fim") if data.get("end") else None,
                title=data.get("title"), location=data.get("location"), notes=data.get("notes"),
                notify_customer=data.get("notify_customer", True) not in (False, "false"), user=request.user,
                force=data.get("force") in (True, "true", "1"),
            )
        except ScheduleConflict as e:
            return Response({"detail": str(e), "conflicts": e.conflicts, "can_force": has_role(request.user)},
                            status=status.HTTP_409_CONFLICT)
        except PermissionDeniedError as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(event)

    def delete(self, request, event_id):
        try:
            return Response(service.cancel(event_id, user=request.user))
        except PermissionDeniedError as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)


class GoogleStatusController(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cfg = LmSettings.get()
        client_ok = True
        try:
            from agenda.services.google_calendar_client import _client_config
            _client_config()
        except GoogleNotConfigured:
            client_ok = False
        return Response({
            "client_configured": client_ok,
            "authorized": bool(refresh_token()),
            "connected": is_configured(),
            "redirect_uri": redirect_uri(),
            "calendar_id": cfg.google_calendar_id or os.getenv("GOOGLE_CALENDAR_ID", "primary"),
        })


class GoogleConnectController(APIView):
    """GET: URL de autorização do Google (só admin). O callback grava o refresh token no LmSettings."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not has_role(request.user):
            return Response({"detail": "Só a Erica (admin) conecta o Google Agenda."}, status=status.HTTP_403_FORBIDDEN)
        state = signing.dumps({"uid": request.user.id}, salt=STATE_SALT)
        try:
            return Response({"url": GoogleCalendarClient().authorization_url(state)})
        except GoogleNotConfigured as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class GoogleCallbackController(APIView):
    """Redirecionamento do Google. Sem JWT: a origem é validada pelo `state` assinado (15 min)."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request):
        front = os.getenv("FRONTEND_URL", "").rstrip("/")
        state = request.query_params.get("state", "")
        try:
            signing.loads(state, salt=STATE_SALT, max_age=15 * 60)
        except signing.BadSignature:
            return Response({"detail": "Autorização inválida ou expirada."}, status=status.HTTP_400_BAD_REQUEST)
        if request.query_params.get("error"):
            return redirect(f"{front}/agenda?google=negado")
        try:
            token = GoogleCalendarClient().exchange_code(request.query_params.get("code", ""), state)
        except Exception as e:
            logger.error(f"[Agenda] Falha no callback OAuth: {e}")
            return redirect(f"{front}/agenda?google=erro")
        cfg = LmSettings.get()
        cfg.google_refresh_token = token
        cfg.google_sync_token = ""
        cfg.save()
        return redirect(f"{front}/agenda?google=ok")


class GoogleSyncController(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            return Response(service.sync_from_google())
        except GoogleNotConfigured as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[Agenda] Falha na sincronização: {e}")
            return Response({"detail": "Falha ao sincronizar com o Google."}, status=status.HTTP_502_BAD_GATEWAY)
