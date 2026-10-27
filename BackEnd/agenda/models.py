from datetime import datetime

from mongoengine import NULLIFY, BooleanField, DateTimeField, DictField, Document, ListField, ReferenceField, StringField

from crm.models.custumer_model import Customer

EVENT_TYPES = {
    "reuniao_online": "Reunião online",
    "visita_tecnica": "Visita técnica",
    "evento_confirmado": "Evento confirmado",
    "bloqueio": "Bloqueio",
    "externo": "Compromisso (Google Agenda)",
}


class CalendarEvent(Document):
    """Espelho local da agenda principal da Erica (conta Contato LM)."""

    meta = {
        'collection': 'calendar_events',
        'strict': False,
        'indexes': ['google_event_id', 'customer', 'start', 'type', ('start', 'end'), 'series_id'],
    }

    google_event_id = StringField(null=True)  # numa série: id da ocorrência no Google (instance id)
    type = StringField(choices=tuple(EVENT_TYPES), required=True)
    title = StringField(required=True)
    customer = ReferenceField(Customer, null=True, reverse_delete_rule=NULLIFY)
    start = DateTimeField(required=True)  # UTC
    end = DateTimeField(required=True)  # UTC
    all_day = BooleanField(default=False)  # início e fim à meia-noite de Brasília
    location = StringField(null=True)
    meet_link = StringField(null=True)
    description = StringField(null=True)
    series_id = StringField(null=True)  # ocorrência de uma EventSeries (evento que se repete)
    original_start = DateTimeField(null=True)  # início previsto pela regra (identifica a ocorrência)
    source = StringField(choices=("lm", "google"), default="lm")
    status = StringField(choices=("confirmado", "cancelado"), default="confirmado")
    sync_status = StringField(choices=("sincronizado", "pendente", "erro", "local"), default="pendente")
    sync_error = StringField(null=True)
    reminders_sent = ListField(StringField())  # ["24h_cliente", "2h_erica", ...]
    created_by = StringField(null=True)
    extra = DictField()
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    def to_dict(self, recurrence: dict | None = None) -> dict:
        return {
            "id": str(self.id),
            "google_event_id": self.google_event_id,
            "type": self.type,
            "type_label": EVENT_TYPES.get(self.type, self.type),
            "title": self.title,
            "customer_id": str(self.customer.id) if self.customer else None,
            "customer_name": getattr(self.customer, "name", None),
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "all_day": bool(self.all_day),
            "series_id": self.series_id,
            "recurrence": recurrence,
            "location": self.location,
            "meet_link": self.meet_link,
            "description": self.description,
            "notes": (self.extra or {}).get("notes"),
            "source": self.source,
            "status": self.status,
            "sync_status": self.sync_status,
            "sync_error": self.sync_error,
        }


class EventSeries(Document):
    """Evento que se repete (como no Google Agenda). As ocorrências são CalendarEvent com `series_id`,
    geradas até `materialized_until` e estendidas sob demanda quando a agenda olha mais adiante."""

    meta = {'collection': 'calendar_series', 'strict': False, 'indexes': ['google_event_id', 'status']}

    type = StringField(choices=tuple(EVENT_TYPES), required=True)
    title = StringField(required=True)
    customer = ReferenceField(Customer, null=True, reverse_delete_rule=NULLIFY)
    start = DateTimeField(required=True)  # UTC, primeira ocorrência
    end = DateTimeField(required=True)  # UTC, fim da primeira ocorrência
    all_day = BooleanField(default=False)
    rule = DictField()  # ver agenda.services.recurrence
    location = StringField(null=True)
    description = StringField(null=True)
    meet_link = StringField(null=True)
    notes = StringField(null=True)
    google_event_id = StringField(null=True)  # evento repetido no Google (as ocorrências derivam dele)
    status = StringField(choices=("confirmado", "cancelado"), default="confirmado")
    materialized_until = DateTimeField(required=True)  # UTC
    created_by = StringField(null=True)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
