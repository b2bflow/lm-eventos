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
    blocked_until = DateTimeField(null=True)
    new_service = BooleanField(default=True)

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
            "blocked_until": self.blocked_until.isoformat() if self.blocked_until else None,
            "new_service": self.new_service,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
