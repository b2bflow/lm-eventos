from datetime import datetime
from mongoengine import (
    BooleanField,
    DateTimeField,
    Document,
    FloatField,
    IntField,
    StringField,
)

class Customer(Document):
    meta = {
        'collection': 'customer',
        'indexes': ['name', 'phone', 'customer_state_now', '-created_at'],
        'strict': False
    }

    name = StringField(max_length=120, null=True)
    phone = StringField(max_length=30, unique=True, required=True)
    agent = StringField(null=True)
    STATE_CHOICES = (
        ('ANALYSIS', 'Analise'),
        ('BUDGET', 'Orcamento'),
        ('NEGOTIATING', 'Negociando'),
        ('WON', 'Venda'),
        ('LOST', 'Perdido'),
    )
    customer_state_now = StringField(choices=STATE_CHOICES, default='ANALYSIS')
    customer_custom_tag = StringField(null=True)
    new_service = BooleanField(default=True)

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

    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)

    def __str__(self) -> str:
        return f"{self.name or 'Sem Nome'} ({self.phone})"

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "phone": self.phone,
            "agent": self.agent,
            "customer_state_now": self.customer_state_now,
            "actual_status": self.customer_state_now,
            "customer_custom_tag": self.customer_custom_tag,
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
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "new_service": self.new_service
        }
