from datetime import datetime

from mongoengine import DateTimeField, DictField, Document, ListField, ReferenceField, StringField

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
        'indexes': ['google_event_id', 'customer', 'start', 'type', ('start', 'end')],
    }

    google_event_id = StringField(null=True)
    type = StringField(choices=tuple(EVENT_TYPES), required=True)
    title = StringField(required=True)
    customer = ReferenceField(Customer, null=True)
    start = DateTimeField(required=True)  # UTC
    end = DateTimeField(required=True)  # UTC
    location = StringField(null=True)
    meet_link = StringField(null=True)
    description = StringField(null=True)
    source = StringField(choices=("lm", "google"), default="lm")
    status = StringField(choices=("confirmado", "cancelado"), default="confirmado")
    sync_status = StringField(choices=("sincronizado", "pendente", "erro", "local"), default="pendente")
    sync_error = StringField(null=True)
    reminders_sent = ListField(StringField())  # ["24h_cliente", "2h_erica", ...]
    created_by = StringField(null=True)
    extra = DictField()
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    def to_dict(self) -> dict:
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
            "location": self.location,
            "meet_link": self.meet_link,
            "description": self.description,
            "source": self.source,
            "status": self.status,
            "sync_status": self.sync_status,
            "sync_error": self.sync_error,
        }
