"""Agenda da Erica: agendamento a partir do card, espelho do Google Agenda, bloqueios fixos e lembretes."""
from datetime import datetime, timedelta

from bson import ObjectId

from agenda.models import EVENT_TYPES, CalendarEvent
from agenda.services.google_calendar_client import (
    GoogleCalendarClient, GoogleNotConfigured, is_configured, parse_google_datetime,
)
from crm.container import CrmContainer
from crm.models.custumer_model import Customer
from crm.models.lm_settings_model import LmSettings
from crm.repositories.log_service_repository import ServiceLogRepository
from crm.services.business_hours import local_tz, to_local, to_utc_naive
from crm.services.notification_service import format_phone
from utils.logger import logger

SCHEDULABLE = ("reuniao_online", "visita_tecnica", "evento_confirmado", "bloqueio")
FLAG_BY_TYPE = {"reuniao_online": "reuniao_agendada", "visita_tecnica": "visita_agendada"}
# Tipos que dependem da Erica no horário: não podem cair em bloqueio fixo, treino ou outro compromisso.
NEEDS_FREE_SLOT = ("reuniao_online", "visita_tecnica")


class ScheduleConflict(ValueError):
    """Horário ocupado na agenda da Erica (bloqueio fixo, reunião, visita ou compromisso do Google)."""

    def __init__(self, conflicts: list[dict]):
        super().__init__("Horário ocupado na agenda da Erica: " + "; ".join(c["title"] for c in conflicts)
                         + ". Escolha outro horário.")
        self.conflicts = conflicts


def _operator(user):
    return str(user.id) if user is not None and getattr(user, "id", None) else None


def _description(notes: str | None, customer: Customer | None) -> str:
    lines = [notes or ""]
    if customer:
        lines.append(f"Contato: {customer.name or ''} {format_phone(customer.phone)}")
    return "\n".join(line for line in lines if line).strip()


def _get_event(event_id: str) -> CalendarEvent:
    try:
        event = CalendarEvent.objects(id=ObjectId(event_id)).first()
    except Exception:
        event = None
    if not event:
        raise ValueError("Evento não encontrado.")
    return event


def _when(dt_utc: datetime) -> str:
    local = to_local(dt_utc)
    return local.strftime("%d/%m/%Y às %H:%M")


class AgendaService:
    def __init__(self, google: GoogleCalendarClient | None = None):
        self.google = google or GoogleCalendarClient()

    # --- Leitura -------------------------------------------------------------------------

    def fixed_blocks(self, start: datetime, end: datetime) -> list[dict]:
        """Bloqueios fixos (treino quarta e sexta 12h) expandidos no período."""
        blocks = []
        tz = local_tz()
        day = to_local(start).date()
        last = to_local(end).date()
        while day <= last:
            for block in LmSettings.get().fixed_blocks or []:
                if block.get("weekday") != day.weekday():
                    continue
                h1, m1 = map(int, block["start"].split(":"))
                h2, m2 = map(int, block["end"].split(":"))
                b_start = to_utc_naive(datetime(day.year, day.month, day.day, h1, m1, tzinfo=tz))
                b_end = to_utc_naive(datetime(day.year, day.month, day.day, h2, m2, tzinfo=tz))
                if b_end > start and b_start < end:
                    blocks.append({
                        "id": f"fixo-{day.isoformat()}-{block['start']}", "type": "bloqueio", "type_label": "Bloqueio fixo",
                        "title": block.get("title", "Bloqueio"), "start": b_start.isoformat(), "end": b_end.isoformat(),
                        "source": "lm", "fixed": True, "status": "confirmado",
                    })
            day += timedelta(days=1)
        return blocks

    def events(self, start: datetime, end: datetime) -> list[dict]:
        events = CalendarEvent.objects(status="confirmado", start__lt=end, end__gt=start).order_by("start")
        return [e.to_dict() for e in events] + self.fixed_blocks(start, end)

    def conflicts(self, start: datetime, end: datetime, ignore_id: str | None = None) -> list[dict]:
        found = [e for e in self.events(start, end) if e.get("id") != ignore_id]
        return [e for e in found if e["type"] != "evento_confirmado"]

    # --- Agendamento ---------------------------------------------------------------------

    def schedule(self, event_type: str, start: datetime, end: datetime, customer_id: str | None = None,
                 title: str | None = None, location: str | None = None, notes: str | None = None,
                 notify_customer: bool = True, user=None, force: bool = False, now: datetime | None = None) -> dict:
        """Cria o compromisso (e no Google, se conectado). Reunião e visita em horário ocupado são
        recusadas com ScheduleConflict; só a Erica (admin) agenda mesmo assim com `force`."""
        from users.permissions import has_role

        if event_type not in SCHEDULABLE:
            raise ValueError("Tipo de agendamento inválido.")
        if end <= start:
            raise ValueError("O fim deve ser depois do início.")
        if end - start > timedelta(days=31):
            raise ValueError("Período longo demais para um compromisso.")
        if event_type == "visita_tecnica" and not location:
            raise ValueError("Informe o endereço da visita técnica.")
        if event_type in NEEDS_FREE_SLOT and start < (now or datetime.utcnow()) - timedelta(minutes=5):
            raise ValueError("Não é possível agendar no passado.")
        try:
            customer = Customer.objects(id=ObjectId(customer_id)).first() if customer_id else None
        except Exception:
            raise ValueError("Lead inválido.")
        if event_type in FLAG_BY_TYPE and not customer:
            raise ValueError("Escolha o lead do agendamento.")
        if event_type in NEEDS_FREE_SLOT:
            clash = self.conflicts(start, end)
            if clash and not (force and has_role(user)):
                raise ScheduleConflict(clash)

        label = EVENT_TYPES[event_type]
        title = title or (f"{label}: {customer.name or format_phone(customer.phone)}" if customer else label)
        event = CalendarEvent(
            type=event_type, title=title, customer=customer, start=start, end=end, location=location,
            description=_description(notes, customer), created_by=_operator(user), sync_status="pendente",
            extra={"notes": notes or ""},
        ).save()

        warnings = []
        clash = self.conflicts(start, end, ignore_id=str(event.id))
        if clash:
            warnings.append("Conflito com: " + "; ".join(c["title"] for c in clash))

        if is_configured():
            try:
                created = self.google.create_event(
                    title, start, end, description=event.description or "", location=location or "",
                    with_meet=event_type == "reuniao_online",
                    attendees=[customer.email] if customer and customer.email else None,
                )
                event.google_event_id = created.get("id")
                event.meet_link = created.get("hangoutLink") or next(
                    (ep.get("uri") for ep in (created.get("conferenceData") or {}).get("entryPoints", [])
                     if ep.get("entryPointType") == "video"), None)
                event.sync_status = "sincronizado"
            except Exception as e:
                logger.error(f"[Agenda] Falha ao criar evento no Google: {e}")
                event.sync_status = "erro"
                event.sync_error = str(e)[:300]
                warnings.append("Não foi possível criar no Google Agenda; o evento ficou só na plataforma.")
        else:
            event.sync_status = "local"
            warnings.append("Google Agenda não conectado: evento salvo só na plataforma.")
        event.save()

        if customer:
            if event_type in FLAG_BY_TYPE:
                CrmContainer.get_pipeline_service().set_flags(str(customer.id), add=[FLAG_BY_TYPE[event_type]], user=user)
            ServiceLogRepository.create_log(
                customer=customer, operator_id=_operator(user), action_type="MEETING_SCHEDULED",
                description=f"{label} agendada para {_when(start)}." + (f" Local: {location}." if location else "")
                + (f" Link: {event.meet_link}" if event.meet_link else ""),
                metadata={"event_id": str(event.id), "type": event_type},
            )
            if notify_customer and event_type in ("reuniao_online", "visita_tecnica"):
                self._notify_customer(event, customer)

        data = event.to_dict()
        data["warnings"] = warnings
        return data

    def _notify_customer(self, event: CalendarEvent, customer: Customer, rescheduled: bool = False):
        name = (customer.name or "").split(" ")[0]
        greeting = f"Olá, {name}." if name and not name.startswith("WhatsApp") else "Olá."
        state = "foi remarcada para" if rescheduled else "está confirmada para"
        if event.type == "reuniao_online":
            lines = [greeting, f"Sua reunião com a LM Eventos {state} {_when(event.start)}."]
            lines.append(f"Link da reunião: {event.meet_link}" if event.meet_link
                         else "O link da reunião será enviado em seguida.")
        else:
            lines = [greeting, f"A visita técnica da LM Eventos {state} {_when(event.start)}.",
                     f"Endereço: {event.location}"]
        lines.append("Qualquer necessidade, estamos à disposição.")
        try:
            CrmContainer.get_notification_service().chat.send_message(phone=customer.phone, message="\n".join(lines))
        except Exception as e:
            logger.error(f"[Agenda] Falha ao avisar o cliente {customer.phone}: {e}")

    def update(self, event_id: str, start: datetime | None = None, end: datetime | None = None,
               title: str | None = None, location: str | None = None, notes: str | None = None,
               notify_customer: bool = True, user=None, force: bool = False, now: datetime | None = None) -> dict:
        """Edita um compromisso criado pela plataforma e aplica no Google (PATCH: Meet e convidados ficam).
        Compromissos vindos do Google são só espelho: editar é no próprio Google Agenda."""
        from crm.services.pipeline_service import PermissionDeniedError
        from users.permissions import has_role

        event = _get_event(event_id)
        if event.source == "google":
            raise PermissionDeniedError("Compromisso criado no Google Agenda: edite direto no Google.")
        if event.status == "cancelado":
            raise ValueError("Evento cancelado não pode ser editado.")
        new_start, new_end = start or event.start, end or event.end
        moved = (new_start, new_end) != (event.start, event.end)
        if new_end <= new_start:
            raise ValueError("O fim deve ser depois do início.")
        if new_end - new_start > timedelta(days=31):
            raise ValueError("Período longo demais para um compromisso.")
        if event.type == "visita_tecnica" and location is not None and not location.strip():
            raise ValueError("Informe o endereço da visita técnica.")
        if moved and event.type in NEEDS_FREE_SLOT:
            if new_start < (now or datetime.utcnow()) - timedelta(minutes=5):
                raise ValueError("Não é possível agendar no passado.")
            clash = self.conflicts(new_start, new_end, ignore_id=str(event.id))
            if clash and not (force and has_role(user)):
                raise ScheduleConflict(clash)

        changes = {}
        if moved:
            event.start, event.end = new_start, new_end
            event.reminders_sent = []  # lembretes de 24 h e 2 h valem para o novo horário
            changes.update(start=new_start, end=new_end)
        if title is not None and title.strip() and title.strip() != event.title:
            event.title = changes["title"] = title.strip()
        if location is not None and (location.strip() or None) != event.location:
            event.location = location.strip() or None
            changes["location"] = event.location or ""
        if notes is not None:
            event.extra = {**(event.extra or {}), "notes": notes}
            description = _description(notes, event.customer)
            if description != (event.description or ""):
                event.description = changes["description"] = description
        event.updated_at = datetime.utcnow()

        warnings = []
        if changes and event.google_event_id and is_configured():
            try:
                self.google.update_event(event.google_event_id, **changes)
                event.sync_status, event.sync_error = "sincronizado", None
            except Exception as e:
                logger.error(f"[Agenda] Falha ao alterar evento no Google: {e}")
                event.sync_status, event.sync_error = "erro", str(e)[:300]
                warnings.append("Não foi possível alterar no Google Agenda; a mudança ficou só na plataforma.")
        elif changes and event.google_event_id:
            warnings.append("Google Agenda não conectado: a mudança ficou só na plataforma.")
        event.save()

        if moved and event.customer:
            ServiceLogRepository.create_log(
                customer=event.customer, operator_id=_operator(user), action_type="MEETING_SCHEDULED",
                description=f"{EVENT_TYPES[event.type]} remarcada para {_when(event.start)}.",
                metadata={"event_id": str(event.id), "type": event.type, "rescheduled": True},
            )
            if notify_customer and event.type in ("reuniao_online", "visita_tecnica"):
                self._notify_customer(event, event.customer, rescheduled=True)

        data = event.to_dict()
        data["warnings"] = warnings
        return data

    def cancel(self, event_id: str, user=None) -> dict:
        from crm.services.pipeline_service import PermissionDeniedError
        from users.permissions import has_role

        event = _get_event(event_id)
        if event.source == "google" and not has_role(user):
            # Compromisso criado direto no Google (pessoal da Erica): cancelar apagaria lá também.
            raise PermissionDeniedError("Compromisso do Google Agenda da Erica: só ela cancela.")
        event.status = "cancelado"
        event.updated_at = datetime.utcnow()
        if event.google_event_id and is_configured():
            try:
                self.google.delete_event(event.google_event_id)
            except Exception as e:
                logger.error(f"[Agenda] Falha ao remover do Google: {e}")
        event.save()
        if event.customer and event.type in FLAG_BY_TYPE:
            CrmContainer.get_pipeline_service().set_flags(str(event.customer.id), remove=[FLAG_BY_TYPE[event.type]], user=user)
        return event.to_dict()

    # --- Sincronização (Google -> plataforma) --------------------------------------------

    def sync_from_google(self) -> dict:
        if not is_configured():
            raise GoogleNotConfigured("Google Agenda não conectado.")
        cfg = LmSettings.get()
        try:
            items, next_token = self.google.list_events(
                time_min=datetime.utcnow() - timedelta(days=30), sync_token=cfg.google_sync_token or None)
        except Exception as e:
            if "410" in str(e) or "fullSyncRequired" in str(e):
                cfg.google_sync_token = ""
                cfg.save()
                items, next_token = self.google.list_events(time_min=datetime.utcnow() - timedelta(days=30))
            else:
                raise
        created = updated = removed = 0
        for item in items:
            existing = CalendarEvent.objects(google_event_id=item["id"]).first()
            if item.get("status") == "cancelled":
                if existing and existing.status != "cancelado":
                    existing.status = "cancelado"
                    existing.save()
                    removed += 1
                continue
            if not item.get("start") or not item.get("end"):
                continue
            fields = {
                "title": item.get("summary") or "(sem título)",
                "start": parse_google_datetime(item["start"]),
                "end": parse_google_datetime(item["end"]),
                "location": item.get("location"),
                "meet_link": item.get("hangoutLink") or (existing.meet_link if existing else None),
                "status": "confirmado",
                "sync_status": "sincronizado",
                "updated_at": datetime.utcnow(),
            }
            if existing:
                for key, value in fields.items():
                    setattr(existing, key, value)
                existing.save()
                updated += 1
            else:
                CalendarEvent(google_event_id=item["id"], type="externo", source="google",
                              description=item.get("description"), **fields).save()
                created += 1
        if next_token:
            cfg.google_sync_token = next_token
            cfg.save()
        return {"created": created, "updated": updated, "removed": removed}

    # --- Lembretes (24 h e 2 h antes) ----------------------------------------------------

    def send_reminders(self, now: datetime | None = None) -> int:
        now = now or datetime.utcnow()
        sent = 0
        notifications = CrmContainer.get_notification_service()
        for key, delta in (("24h", timedelta(hours=24)), ("2h", timedelta(hours=2))):
            window = CalendarEvent.objects(status="confirmado", type__in=["reuniao_online", "visita_tecnica"],
                                           start__gt=now, start__lte=now + delta)
            for event in window:
                done = set(event.reminders_sent or [])
                label = EVENT_TYPES[event.type].lower()
                if f"{key}_erica" not in done:
                    who = event.customer.name if event.customer else event.title
                    notifications.notify_erica("\n".join([
                        f"Lembrete: {label} em {_when(event.start)}.",
                        f"Cliente: {who}",
                        f"Local: {event.location}" if event.location else f"Link: {event.meet_link or 'a definir'}",
                    ]))
                    done.add(f"{key}_erica")
                    sent += 1
                if event.customer and f"{key}_cliente" not in done:
                    lines = [f"Lembrete: sua {label} com a LM Eventos é em {_when(event.start)}."]
                    if event.meet_link:
                        lines.append(f"Link: {event.meet_link}")
                    elif event.location:
                        lines.append(f"Endereço: {event.location}")
                    try:
                        notifications.chat.send_message(phone=event.customer.phone, message="\n".join(lines))
                    except Exception as e:
                        logger.error(f"[Agenda] Falha no lembrete do cliente: {e}")
                    done.add(f"{key}_cliente")
                    sent += 1
                event.reminders_sent = sorted(done)
                event.save()
        return sent

    def confirmed_event_dates(self, start: datetime, end: datetime) -> set:
        """Datas com evento confirmado (alimenta a ocupação de agenda do dashboard)."""
        events = CalendarEvent.objects(status="confirmado", type="evento_confirmado", start__lt=end, end__gt=start)
        return {to_local(e.start).date().isoformat() for e in events}
