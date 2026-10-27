"""Agenda da Erica: agendamento a partir do card, eventos que se repetem, espelho do Google Agenda e lembretes."""
from datetime import date, datetime, time, timedelta

from bson import ObjectId

from agenda.models import EVENT_TYPES, CalendarEvent, EventSeries
from agenda.services import recurrence as rec
from agenda.services.google_calendar_client import (
    ORIGIN_KEY, ORIGIN_VALUE, GoogleCalendarClient, GoogleNotConfigured, is_configured, parse_google_datetime,
    refresh_token, revoke_token,
)
from crm.container import CrmContainer
from crm.models.custumer_model import Customer
from crm.models.lm_settings_model import LmSettings
from crm.repositories.log_service_repository import ServiceLogRepository
from crm.services.business_hours import to_local, to_utc_naive
from crm.services.notification_service import format_phone
from utils.logger import logger

SCHEDULABLE = ("reuniao_online", "visita_tecnica", "evento_confirmado", "bloqueio")
FLAG_BY_TYPE = {"reuniao_online": "reuniao_agendada", "visita_tecnica": "visita_agendada"}
# Tipos que dependem da Erica no horário: não podem cair em bloqueio, outro compromisso ou evento do Google.
NEEDS_FREE_SLOT = ("reuniao_online", "visita_tecnica")
# Alcance da edição/cancelamento numa série, como no Google: este evento, este e os seguintes, todos.
SCOPES = ("this", "following", "all")
HORIZON = timedelta(days=365)  # ocorrências geradas adiante; depois disso, sob demanda (extend_series)
KEEP = object()  # PATCH sem `recurrence`: a repetição fica como está


class ScheduleConflict(ValueError):
    """Horário ocupado na agenda da Erica (bloqueio, reunião, visita ou compromisso do Google)."""

    def __init__(self, conflicts: list[dict]):
        shown = [f"{c['title']} ({to_local(datetime.fromisoformat(c['start'])):%d/%m %H:%M})" for c in conflicts[:3]]
        more = f" e mais {len(conflicts) - 3}" if len(conflicts) > 3 else ""
        super().__init__("Horário ocupado na agenda da Erica: " + "; ".join(shown) + more + ". Escolha outro horário.")
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


def _get_series(series_id: str) -> EventSeries:
    series = EventSeries.objects(id=ObjectId(series_id)).first() if ObjectId.is_valid(series_id or "") else None
    if not series:
        raise ValueError("Repetição do evento não encontrada.")
    return series


def _when(dt_utc: datetime) -> str:
    local = to_local(dt_utc)
    return local.strftime("%d/%m/%Y às %H:%M")


def _midnight(day: date) -> datetime:
    return to_utc_naive(datetime.combine(day, time()))


def _all_day_bounds(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """Dia inteiro: da meia-noite (Brasília) do primeiro dia à meia-noite depois do último (fim exclusivo)."""
    first = to_local(start).date()
    end_local = to_local(end)
    last = end_local.date() if end_local.time() == time() else end_local.date() + timedelta(days=1)
    return _midnight(first), _midnight(max(last, first + timedelta(days=1)))


def _horizon(start: datetime) -> datetime:
    return max(start, datetime.utcnow()) + HORIZON


def _meet_link(created: dict) -> str | None:
    return created.get("hangoutLink") or next(
        (ep.get("uri") for ep in (created.get("conferenceData") or {}).get("entryPoints", [])
         if ep.get("entryPointType") == "video"), None)


def _validate(event_type: str, start: datetime, end: datetime, location: str | None):
    if end <= start:
        raise ValueError("O fim deve ser depois do início.")
    if end - start > timedelta(days=31):
        raise ValueError("Período longo demais para um compromisso.")
    if event_type == "visita_tecnica" and not (location or "").strip():
        raise ValueError("Informe o endereço da visita técnica.")


class AgendaService:
    def __init__(self, google: GoogleCalendarClient | None = None):
        self.google = google or GoogleCalendarClient()

    # --- Leitura -------------------------------------------------------------------------

    def _serialize(self, events: list[CalendarEvent]) -> list[dict]:
        ids = {e.series_id for e in events if e.series_id and ObjectId.is_valid(e.series_id)}
        rules = {str(s.id): s.rule for s in EventSeries.objects(id__in=[ObjectId(i) for i in ids])} if ids else {}
        return [e.to_dict(recurrence=rules.get(e.series_id)) for e in events]

    def _dict(self, event: CalendarEvent, warnings: list[str]) -> dict:
        data = self._serialize([event])[0]
        data["warnings"] = warnings
        return data

    def events(self, start: datetime, end: datetime) -> list[dict]:
        self.extend_series(end)
        return self._serialize(list(CalendarEvent.objects(status="confirmado", start__lt=end, end__gt=start).order_by("start")))

    def _clashes(self, slots: list[tuple[datetime, datetime]], ignore_ids=()) -> list[dict]:
        """Compromissos que ocupam algum dos horários (evento confirmado não ocupa a Erica)."""
        if not slots:
            return []
        first, last = min(s for s, _ in slots), max(e for _, e in slots)
        self.extend_series(last)
        ignore = {str(i) for i in ignore_ids}
        busy = CalendarEvent.objects(status="confirmado", type__ne="evento_confirmado", start__lt=last, end__gt=first)
        found = [e for e in busy.order_by("start")
                 if str(e.id) not in ignore and any(e.start < end and e.end > start for start, end in slots)]
        return [e.to_dict() for e in found]

    def conflicts(self, start: datetime, end: datetime, ignore_id: str | None = None) -> list[dict]:
        return self._clashes([(start, end)], [ignore_id] if ignore_id else [])

    def _check_free(self, event_type: str, slots: list, ignore_ids, user, force: bool, now: datetime | None) -> list[dict]:
        """Reunião e visita não caem em horário ocupado (só a Erica força). Devolve os conflitos aceitos."""
        from users.permissions import has_role
        future = [(s, e) for s, e in slots if e > (now or datetime.utcnow())]
        clash = self._clashes(future, ignore_ids)
        if clash and event_type in NEEDS_FREE_SLOT and not (force and has_role(user)):
            raise ScheduleConflict(clash)
        return clash

    # --- Séries (eventos que se repetem) ---------------------------------------------------

    @staticmethod
    def _starts(rule: dict | None, start: datetime, horizon: datetime) -> list[datetime]:
        if not rule:
            return [start]
        starts = rec.occurrence_starts(rule, start, horizon)
        if not starts:
            raise ValueError("A repetição escolhida não gera nenhuma data.")
        return starts

    @staticmethod
    def _create_occurrences(series: EventSeries, starts: list[datetime], sync_status: str | None = None,
                            sync_error: str | None = None) -> list[CalendarEvent]:
        duration = series.end - series.start
        linked = bool(series.google_event_id) and sync_status in (None, "sincronizado")
        docs = [CalendarEvent(
            type=series.type, title=series.title, customer=series.customer, start=s, end=s + duration,
            all_day=series.all_day, location=series.location, meet_link=series.meet_link,
            description=series.description, series_id=str(series.id), original_start=s, created_by=series.created_by,
            google_event_id=rec.instance_id(series.google_event_id, s, series.all_day) if linked else None,
            sync_status="sincronizado" if linked else (sync_status or "local"), sync_error=sync_error,
            extra={"notes": series.notes or ""},
        ) for s in starts]
        return CalendarEvent.objects.insert(docs, load_bulk=True) if docs else []

    def extend_series(self, until: datetime) -> int:
        """Gera as ocorrências das séries até `until` (agenda olhando mais adiante, lembretes)."""
        created = 0
        for series in EventSeries.objects(status="confirmado", materialized_until__lt=until):
            starts = rec.occurrence_starts(series.rule, series.start, until, after_utc=series.materialized_until)
            created += len(self._create_occurrences(series, starts))
            series.materialized_until = until
            series.save()
        return created

    # --- Google ----------------------------------------------------------------------------

    def _google_create(self, event_type: str, title: str, start: datetime, end: datetime, description: str,
                       location: str | None, customer: Customer | None, all_day: bool, rule: dict | None):
        """Cria no Google (evento único ou repetido). Devolve (id, link do Meet, sync_status, erro, avisos)."""
        if not is_configured():
            return None, None, "local", None, ["Google Agenda não conectado: evento salvo só na plataforma."]
        try:
            created = self.google.create_event(
                title, start, end, description=description or "", location=location or "",
                with_meet=event_type == "reuniao_online",
                attendees=[customer.email] if customer and customer.email else None,
                all_day=all_day, recurrence=rec.to_rrule(rule, start, all_day) if rule else None,
            )
            return created.get("id"), _meet_link(created), "sincronizado", None, []
        except Exception as e:
            logger.error(f"[Agenda] Falha ao criar evento no Google: {e}")
            return None, None, "erro", str(e)[:300], ["Não foi possível criar no Google Agenda; o evento ficou só na plataforma."]

    def _push(self, action, warnings: list[str]) -> str | None:
        """Aplica uma mudança no Google. None = aplicada; senão o motivo (e o aviso vai para `warnings`)."""
        if not is_configured():
            warnings.append("Google Agenda não conectado: a mudança ficou só na plataforma.")
            return "não conectado"
        try:
            action()
            return None
        except Exception as e:
            logger.error(f"[Agenda] Falha ao alterar no Google: {e}")
            warnings.append("Não foi possível alterar no Google Agenda; a mudança ficou só na plataforma.")
            return str(e)[:300]

    @staticmethod
    def _sync_state(error: str | None) -> tuple[str, str | None]:
        if error is None:
            return "sincronizado", None
        return ("erro", error) if is_configured() else ("local", None)

    # --- Agendamento ---------------------------------------------------------------------

    def schedule(self, event_type: str, start: datetime, end: datetime, customer_id: str | None = None,
                 title: str | None = None, location: str | None = None, notes: str | None = None,
                 notify_customer: bool = True, user=None, force: bool = False, now: datetime | None = None,
                 all_day: bool = False, recurrence: dict | None = None) -> dict:
        """Cria o compromisso, único ou repetido (`recurrence`), e no Google se conectado. Reunião e visita em
        horário ocupado são recusadas com ScheduleConflict; só a Erica (admin) agenda mesmo assim com `force`."""
        if event_type not in SCHEDULABLE:
            raise ValueError("Tipo de agendamento inválido.")
        if all_day:
            start, end = _all_day_bounds(start, end)
        _validate(event_type, start, end, location)
        if event_type in NEEDS_FREE_SLOT and start < (now or datetime.utcnow()) - timedelta(minutes=5):
            raise ValueError("Não é possível agendar no passado.")
        try:
            customer = Customer.objects(id=ObjectId(customer_id)).first() if customer_id else None
        except Exception:
            raise ValueError("Lead inválido.")
        if event_type in FLAG_BY_TYPE and not customer:
            raise ValueError("Escolha o lead do agendamento.")

        rule = rec.clean_rule(recurrence, start)
        horizon = _horizon(start)
        starts = self._starts(rule, start, horizon)
        duration = end - start
        start, end = starts[0], starts[0] + duration
        clash = self._check_free(event_type, [(s, s + duration) for s in starts], [], user, force, now)
        warnings = ["Conflito com: " + "; ".join(c["title"] for c in clash[:3])] if clash else []

        label = EVENT_TYPES[event_type]
        title = (title or "").strip() or (f"{label}: {customer.name or format_phone(customer.phone)}" if customer else label)
        description = _description(notes, customer)
        google_id, meet_link, sync_status, sync_error, google_warnings = self._google_create(
            event_type, title, start, end, description, location, customer, all_day, rule)
        warnings += google_warnings
        common = dict(type=event_type, title=title, customer=customer, location=location, description=description,
                      meet_link=meet_link, created_by=_operator(user), all_day=all_day)
        if rule:
            series = EventSeries(**common, start=start, end=end, rule=rule, notes=notes or "",
                                 google_event_id=google_id, materialized_until=horizon).save()
            event = self._create_occurrences(series, starts, sync_status, sync_error)[0]
        else:
            event = CalendarEvent(**common, start=start, end=end, google_event_id=google_id, sync_status=sync_status,
                                  sync_error=sync_error, extra={"notes": notes or ""}).save()

        if customer:
            if event_type in FLAG_BY_TYPE:
                CrmContainer.get_pipeline_service().set_flags(str(customer.id), add=[FLAG_BY_TYPE[event_type]], user=user)
            ServiceLogRepository.create_log(
                customer=customer, operator_id=_operator(user), action_type="MEETING_SCHEDULED",
                description=f"{label} agendada para {_when(start)}." + (" Repete." if rule else "")
                + (f" Local: {location}." if location else "") + (f" Link: {event.meet_link}" if event.meet_link else ""),
                metadata={"event_id": str(event.id), "type": event_type},
            )
            if notify_customer and event_type in ("reuniao_online", "visita_tecnica"):
                self._notify_customer(event, customer)
        return self._dict(event, warnings)

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

    def _rescheduled(self, event: CalendarEvent, user, notify_customer: bool):
        if not event.customer:
            return
        ServiceLogRepository.create_log(
            customer=event.customer, operator_id=_operator(user), action_type="MEETING_SCHEDULED",
            description=f"{EVENT_TYPES[event.type]} remarcada para {_when(event.start)}.",
            metadata={"event_id": str(event.id), "type": event.type, "rescheduled": True},
        )
        if notify_customer and event.type in ("reuniao_online", "visita_tecnica"):
            self._notify_customer(event, event.customer, rescheduled=True)

    # --- Edição ------------------------------------------------------------------------------

    def update(self, event_id: str, start: datetime | None = None, end: datetime | None = None,
               title: str | None = None, location: str | None = None, notes: str | None = None,
               notify_customer: bool = True, user=None, force: bool = False, now: datetime | None = None,
               all_day: bool | None = None, recurrence=KEEP, scope: str = "this") -> dict:
        """Edita um compromisso da plataforma e aplica no Google (PATCH: Meet e convidados ficam).

        Numa série, `scope` é o alcance, como no Google: "this" (só esta ocorrência), "following" (esta e as
        seguintes: a série é cortada aqui e continua numa nova) ou "all" (todas). `recurrence` (regra ou None)
        muda a repetição; sem ela, fica como está. Compromissos vindos do Google são só espelho."""
        from crm.services.pipeline_service import PermissionDeniedError

        event = _get_event(event_id)
        if event.source == "google":
            raise PermissionDeniedError("Compromisso criado no Google Agenda: edite direto no Google.")
        if event.status == "cancelado":
            raise ValueError("Evento cancelado não pode ser editado.")
        if scope not in SCOPES:
            raise ValueError("Escolha quais eventos alterar.")
        series = _get_series(event.series_id) if event.series_id else None
        all_day = bool(event.all_day) if all_day is None else bool(all_day)
        new_start, new_end = start or event.start, end or event.end
        if all_day:
            new_start, new_end = _all_day_bounds(new_start, new_end)
        new = {
            "start": new_start, "end": new_end, "all_day": all_day,
            "title": title.strip() if title and title.strip() else event.title,
            "location": (location.strip() or None) if location is not None else event.location,
            "notes": notes if notes is not None else (event.extra or {}).get("notes") or "",
        }
        _validate(event.type, new_start, new_end, new["location"])
        moved = (new_start, new_end, all_day) != (event.start, event.end, bool(event.all_day))
        current_rule = series.rule if series else None
        rule = current_rule if recurrence is KEEP else rec.clean_rule(recurrence, new_start)
        if moved and event.type in NEEDS_FREE_SLOT and new_start < (now or datetime.utcnow()) - timedelta(minutes=5):
            raise ValueError("Não é possível agendar no passado.")
        ctx = dict(moved=moved, notify_customer=notify_customer, user=user, force=force, now=now)

        if (series and scope == "this") or (not series and not rule):
            if series and rule != current_rule:
                raise ValueError("Para mudar a repetição, escolha \"Este e os seguintes\" ou \"Todos os eventos\".")
            return self._update_one(event, new, **ctx)
        if not series:
            return self._convert_to_series(event, new, rule, **ctx)
        if scope == "following" and event.original_start and event.original_start > series.start:
            return self._split_series(series, event, new, rule, **ctx)
        if not rule:
            return self._detach(series, event, new, **ctx)
        return self._update_series(series, event, new, rule, **ctx)

    def _update_one(self, event: CalendarEvent, new: dict, moved, notify_customer, user, force, now) -> dict:
        """Um evento só (ou uma ocorrência: no Google vira exceção da série)."""
        if moved:
            self._check_free(event.type, [(new["start"], new["end"])], [event.id], user, force, now)
        changes = {}
        if moved:
            event.start, event.end, event.all_day = new["start"], new["end"], new["all_day"]
            event.reminders_sent = []  # lembretes de 24 h e 2 h valem para o novo horário
            changes.update(start=new["start"], end=new["end"], all_day=new["all_day"])
        if new["title"] != event.title:
            event.title = changes["title"] = new["title"]
        if new["location"] != event.location:
            event.location = new["location"]
            changes["location"] = new["location"] or ""
        if new["notes"] != ((event.extra or {}).get("notes") or ""):
            event.extra = {**(event.extra or {}), "notes": new["notes"]}
            description = _description(new["notes"], event.customer)
            if description != (event.description or ""):
                event.description = changes["description"] = description
        event.updated_at = datetime.utcnow()
        warnings = []
        if changes and event.google_event_id:
            error = self._push(lambda: self.google.update_event(event.google_event_id, **changes), warnings)
            if error is None or is_configured():
                event.sync_status, event.sync_error = self._sync_state(error)
        event.save()
        if moved:
            self._rescheduled(event, user, notify_customer)
        return self._dict(event, warnings)

    def _new_series(self, template, new: dict, rule: dict, starts: list[datetime], warnings: list[str],
                    google_id: str | None = None, meet_link: str | None = None,
                    sync_status: str | None = None, sync_error: str | None = None) -> list[CalendarEvent]:
        """Grava a série (dados de `template` com `new` aplicado) e as ocorrências. Sem `google_id` nem
        `sync_status`, cria o evento repetido no Google."""
        duration = new["end"] - new["start"]
        description = _description(new["notes"], template.customer)
        if google_id is None and sync_status is None:
            google_id, meet_link, sync_status, sync_error, google_warnings = self._google_create(
                template.type, new["title"], starts[0], starts[0] + duration, description, new["location"],
                template.customer, new["all_day"], rule)
            warnings += google_warnings
        series = EventSeries(
            type=template.type, title=new["title"], customer=template.customer, start=starts[0],
            end=starts[0] + duration, all_day=new["all_day"], rule=rule, location=new["location"],
            description=description, meet_link=meet_link or template.meet_link, notes=new["notes"],
            google_event_id=google_id, created_by=template.created_by, materialized_until=_horizon(new["start"]),
        ).save()
        return self._create_occurrences(series, starts, sync_status, sync_error)

    @staticmethod
    def _edited(occurrences: list[CalendarEvent], start: datetime) -> CalendarEvent:
        """A ocorrência que corresponde ao evento editado (a primeira a partir do novo início)."""
        return next((o for o in occurrences if o.start >= start), occurrences[0])

    def _convert_to_series(self, event: CalendarEvent, new: dict, rule: dict, moved, notify_customer, user, force, now) -> dict:
        """Evento único passa a se repetir. No Google o mesmo evento ganha a regra (Meet e convidados ficam)."""
        starts = self._starts(rule, new["start"], _horizon(new["start"]))
        duration = new["end"] - new["start"]
        self._check_free(event.type, [(s, s + duration) for s in starts], [event.id], user, force, now)
        warnings = []
        google_id = status = error = None
        if event.google_event_id:
            description = _description(new["notes"], event.customer)
            error = self._push(lambda: self.google.update_event(
                event.google_event_id, title=new["title"], start=starts[0], end=starts[0] + duration,
                description=description, location=new["location"] or "", all_day=new["all_day"],
                recurrence=rec.to_rrule(rule, starts[0], new["all_day"])), warnings)
            google_id = event.google_event_id if error is None else None
            status, error = self._sync_state(error)
        occurrences = self._new_series(event, new, rule, starts, warnings, google_id, event.meet_link, status, error)
        event.delete()
        target = self._edited(occurrences, new["start"])
        if moved:
            self._rescheduled(target, user, notify_customer)
        return self._dict(target, warnings)

    def _update_series(self, series: EventSeries, event: CalendarEvent, new: dict, rule: dict,
                       moved, notify_customer, user, force, now) -> dict:
        """Todos os eventos: o mesmo evento repetido no Google; aqui as ocorrências são refeitas se a data,
        o horário ou a regra mudarem (o deslocamento do evento editado vale para a série toda)."""
        sid = str(series.id)
        duration = new["end"] - new["start"]
        first = series.start + (new["start"] - event.start)
        regenerate = moved or rule != series.rule
        warnings, changes = [], {}
        if regenerate:
            horizon = _horizon(first)
            starts = self._starts(rule, first, horizon)
            ids = [e.id for e in CalendarEvent.objects(series_id=sid).only("id")]
            self._check_free(series.type, [(s, s + duration) for s in starts], ids, user, force, now)
            changes.update(start=starts[0], end=starts[0] + duration, all_day=new["all_day"],
                           recurrence=rec.to_rrule(rule, starts[0], new["all_day"]))
        description = _description(new["notes"], series.customer)
        if new["title"] != series.title:
            changes["title"] = new["title"]
        if new["location"] != series.location:
            changes["location"] = new["location"] or ""
        if description != (series.description or ""):
            changes["description"] = description
        error = None
        if changes and series.google_event_id:
            error = self._push(lambda: self.google.update_event(series.google_event_id, **changes), warnings)
        series.title, series.location, series.notes, series.description = new["title"], new["location"], new["notes"], description
        series.updated_at = datetime.utcnow()
        if not regenerate:
            series.save()
            CalendarEvent.objects(series_id=sid).update(
                set__title=new["title"], set__location=new["location"], set__description=description,
                set__extra__notes=new["notes"], set__updated_at=datetime.utcnow())
            return self._dict(event.reload(), warnings)
        series.start, series.end, series.all_day, series.rule = starts[0], starts[0] + duration, new["all_day"], rule
        series.materialized_until = horizon
        series.save()
        CalendarEvent.objects(series_id=sid).delete()
        status, sync_error = self._sync_state(error) if series.google_event_id else ("local", None)
        target = self._edited(self._create_occurrences(series, starts, status, sync_error), new["start"])
        if moved:
            self._rescheduled(target, user, notify_customer)
        return self._dict(target, warnings)

    def _split_series(self, series: EventSeries, event: CalendarEvent, new: dict, rule: dict | None,
                      moved, notify_customer, user, force, now) -> dict:
        """Este e os seguintes: a série termina na véspera desta ocorrência e o resto vira outro evento
        (repetido ou não), como o Google faz."""
        sid, cut = str(series.id), event.original_start
        tail_rule = rec.remaining_count(series.rule, series.start, cut) if rule == series.rule else rule
        duration = new["end"] - new["start"]
        starts = self._starts(tail_rule, new["start"], _horizon(new["start"]))
        removed = [e.id for e in CalendarEvent.objects(series_id=sid, original_start__gte=cut).only("id")]
        self._check_free(series.type, [(s, s + duration) for s in starts], removed, user, force, now)

        warnings = []
        series.rule = rec.truncate_before(series.rule, cut)
        series.updated_at = datetime.utcnow()
        if series.google_event_id:
            self._push(lambda: self.google.update_event(
                series.google_event_id, recurrence=rec.to_rrule(series.rule, series.start, series.all_day)), warnings)
        series.save()
        CalendarEvent.objects(id__in=removed).delete()

        if tail_rule:
            target = self._edited(self._new_series(series, new, tail_rule, starts, warnings), new["start"])
        else:
            description = _description(new["notes"], series.customer)
            google_id, meet_link, status, error, google_warnings = self._google_create(
                series.type, new["title"], new["start"], new["end"], description, new["location"], series.customer,
                new["all_day"], None)
            warnings += google_warnings
            target = CalendarEvent(
                type=series.type, title=new["title"], customer=series.customer, start=new["start"], end=new["end"],
                all_day=new["all_day"], location=new["location"], description=description,
                meet_link=meet_link or series.meet_link, google_event_id=google_id, sync_status=status,
                sync_error=error, created_by=series.created_by, extra={"notes": new["notes"]},
            ).save()
        if moved:
            self._rescheduled(target, user, notify_customer)
        return self._dict(target, warnings)

    def _detach(self, series: EventSeries, event: CalendarEvent, new: dict, moved, notify_customer, user, force, now) -> dict:
        """Todos os eventos com "Não se repete": fica só este, e o evento repetido do Google vira um evento só."""
        if moved:
            self._check_free(event.type, [(new["start"], new["end"])], [event.id], user, force, now)
        warnings = []
        description = _description(new["notes"], series.customer)
        error = None
        if series.google_event_id:
            error = self._push(lambda: self.google.update_event(
                series.google_event_id, title=new["title"], start=new["start"], end=new["end"], all_day=new["all_day"],
                description=description, location=new["location"] or "", recurrence=[]), warnings)
        CalendarEvent.objects(series_id=str(series.id), id__ne=event.id).delete()
        event.series_id = event.original_start = None
        event.google_event_id = series.google_event_id if error is None else None
        event.sync_status, event.sync_error = self._sync_state(error) if series.google_event_id else ("local", None)
        event.start, event.end, event.all_day = new["start"], new["end"], new["all_day"]
        event.title, event.location, event.description = new["title"], new["location"], description
        event.extra = {**(event.extra or {}), "notes": new["notes"]}
        event.updated_at = datetime.utcnow()
        if moved:
            event.reminders_sent = []
        event.save()
        series.delete()
        if moved:
            self._rescheduled(event, user, notify_customer)
        return self._dict(event, warnings)

    # --- Cancelamento ------------------------------------------------------------------------

    def cancel(self, event_id: str, user=None, scope: str = "this") -> dict:
        """Cancela o compromisso. Numa série, `scope` como na edição (só este, este e os seguintes, todos)."""
        from crm.services.pipeline_service import PermissionDeniedError
        from users.permissions import has_role

        event = _get_event(event_id)
        if event.source == "google" and not has_role(user):
            # Compromisso criado direto no Google (pessoal da Erica): cancelar apagaria lá também.
            raise PermissionDeniedError("Compromisso do Google Agenda da Erica: só ela cancela.")
        if scope not in SCOPES:
            raise ValueError("Escolha quais eventos cancelar.")
        now = datetime.utcnow()
        series = _get_series(event.series_id) if event.series_id and scope != "this" else None
        if series is None:
            event.status = "cancelado"
            event.updated_at = now
            if event.google_event_id and is_configured():
                try:
                    self.google.delete_event(event.google_event_id)
                except Exception as e:
                    logger.error(f"[Agenda] Falha ao remover do Google: {e}")
            event.save()
        elif scope == "all" or not event.original_start or event.original_start <= series.start:
            series.status = "cancelado"
            series.updated_at = now
            series.save()
            CalendarEvent.objects(series_id=str(series.id), status="confirmado").update(
                set__status="cancelado", set__updated_at=now)
            if series.google_event_id and is_configured():
                try:
                    self.google.delete_event(series.google_event_id)
                except Exception as e:
                    logger.error(f"[Agenda] Falha ao remover a série do Google: {e}")
        else:
            series.rule = rec.truncate_before(series.rule, event.original_start)
            series.updated_at = now
            series.save()
            CalendarEvent.objects(series_id=str(series.id), original_start__gte=event.original_start,
                                  status="confirmado").update(set__status="cancelado", set__updated_at=now)
            if series.google_event_id:
                self._push(lambda: self.google.update_event(
                    series.google_event_id, recurrence=rec.to_rrule(series.rule, series.start, series.all_day)), [])
        event.reload()
        # A etiqueta do card sai quando não sobra outra reunião/visita do mesmo tipo pela frente.
        if event.customer and event.type in FLAG_BY_TYPE and not CalendarEvent.objects(
                customer=event.customer, type=event.type, status="confirmado", start__gte=now).count():
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
            existing = CalendarEvent.objects(google_event_id=item["id"]).first() or self._own_occurrence(item)
            own = ((item.get("extendedProperties") or {}).get("private") or {}).get(ORIGIN_KEY) == ORIGIN_VALUE
            if not existing and (own or self._own_series(item)):
                continue  # evento da plataforma que não está mais aqui (ou ocorrência além do que já foi gerado)
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
                "all_day": "date" in item["start"],
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
        cfg.google_last_sync_at = datetime.utcnow()
        cfg.save()
        return {"created": created, "updated": updated, "removed": removed}

    @staticmethod
    def _own_series(item: dict) -> EventSeries | None:
        return EventSeries.objects(google_event_id=item["recurringEventId"]).first() if item.get("recurringEventId") else None

    def _own_occurrence(self, item: dict) -> CalendarEvent | None:
        """Ocorrência de uma série da plataforma pelo início original, caso o id da instância não bata."""
        series = self._own_series(item)
        if not series or not item.get("originalStartTime"):
            return None
        event = CalendarEvent.objects(series_id=str(series.id),
                                      original_start=parse_google_datetime(item["originalStartTime"])).first()
        if event:
            event.google_event_id = item["id"]
        return event

    def disconnect(self) -> dict:
        """Desconecta a conta: revoga o acesso no Google, apaga o token e tira o espelho dos compromissos
        vindos do Google. Eventos criados pela plataforma ficam (e continuam no Google)."""
        cfg = LmSettings.get()
        token = cfg.google_refresh_token
        if not token:
            if refresh_token():
                raise ValueError("A conexão vem da variável GOOGLE_REFRESH_TOKEN do servidor: remova-a no Easypanel.")
            raise ValueError("Google Agenda já está desconectado.")
        revoke_token(token)
        cfg.google_refresh_token = ""
        cfg.google_sync_token = ""
        cfg.google_last_sync_at = None
        cfg.save()
        removed = CalendarEvent.objects(source="google").delete()
        return {"disconnected": True, "mirror_removed": removed}

    # --- Lembretes (24 h e 2 h antes) ----------------------------------------------------

    def send_reminders(self, now: datetime | None = None) -> int:
        now = now or datetime.utcnow()
        self.extend_series(now + timedelta(days=2))  # séries longas: garante as ocorrências dos próximos dias
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
