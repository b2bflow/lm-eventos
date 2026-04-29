from datetime import datetime
from mongoengine import (
    DateTimeField,
    Document,
    FloatField,
    IntField,
    ReferenceField,
    StringField,
)
from crm.models.custumer_model import Customer


class Quote(Document):
    meta = {
        "collection": "quotes",
        "indexes": ["customer", "status", "-created_at", "-updated_at"],
        "strict": False,
    }

    customer = ReferenceField(Customer, required=True)

    STATUS_CHOICES = (
        ("ANALYSIS", "Analise"),
        ("BUDGET", "Orcamento"),
        ("NEGOTIATING", "Negociando"),
        ("WON", "Venda"),
        ("LOST", "Perdido"),
    )
    status = StringField(choices=STATUS_CHOICES, default="ANALYSIS")

    celebration_type = StringField(max_length=80, null=True)
    event_title = StringField(max_length=140, null=True)
    event_date = DateTimeField(null=True)
    guest_count = IntField(default=0)
    quoted_amount = FloatField(default=0)
    contract_value = FloatField(default=0)
    venue = StringField(max_length=160, null=True)
    notes = StringField(null=True)
    proposal_sent_at = DateTimeField(null=True)
    last_interaction_at = DateTimeField(null=True)
    next_step = StringField(max_length=160, null=True)
    closed_at = DateTimeField(null=True)

    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "quote_id": str(self.id),
            "customer": str(self.customer.id) if self.customer else None,
            "customer_id": str(self.customer.id) if self.customer else None,
            "name": getattr(self.customer, "name", None),
            "phone": getattr(self.customer, "phone", None),
            "customer_state_now": self.status,
            "actual_status": self.status,
            "status": self.status,
            "customer_custom_tag": getattr(self.customer, "customer_custom_tag", None),
            "celebration_type": self.celebration_type,
            "event_title": self.event_title,
            "event_date": self.event_date.isoformat() if self.event_date else None,
            "guest_count": self.guest_count,
            "quoted_amount": self.quoted_amount or 0,
            "contract_value": self.contract_value or 0,
            "venue": self.venue,
            "notes": self.notes,
            "proposal_sent_at": self.proposal_sent_at.isoformat() if self.proposal_sent_at else None,
            "last_interaction_at": self.last_interaction_at.isoformat() if self.last_interaction_at else None,
            "next_step": self.next_step,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
