from datetime import datetime
from mongoengine import (
    BooleanField,
    DateTimeField,
    DictField,
    Document,
    FloatField,
    IntField,
    ListField,
    StringField,
)

from crm import domain


def _iso(value):
    return value.isoformat() if value else None


class Customer(Document):
    """Contato e o lead em andamento dele. Leads anteriores do contato ficam em `opportunities`
    (crm.models.opportunity_model.Opportunity)."""

    meta = {
        'collection': 'customer',
        'indexes': [
            'name', 'phone', 'customer_state_now', '-created_at',
            'product', 'owner', 'human_operator', 'flags', 'next_action_at', 'funnel_entered_at',
        ],
        'strict': False
    }

    name = StringField(max_length=120, null=True)
    phone = StringField(max_length=30, unique=True, required=True)
    agent = StringField(null=True)
    STATE_CHOICES = tuple((s, domain.STAGE_LABELS[s]) for s in domain.STAGES) + tuple(
        (s, f'{s} (antigo)') for s in domain.LEGACY_STAGES
    )
    customer_state_now = StringField(choices=STATE_CHOICES, default=domain.NEW_LEAD)
    customer_custom_tag = StringField(null=True)
    blocked_until = DateTimeField(null=True)
    silenced_until = DateTimeField(null=True)
    new_service = BooleanField(default=True)

    send_button = BooleanField(default=True)
    waiting_for_name = BooleanField(default=False)
    name_collected = BooleanField(default=False)

    last_message_attendant = DateTimeField(null=True)
    followup_sent = BooleanField(default=False)

    # --- Evento do lead atual (espelhado da cotacao ativa, ver crm.services.quote_sync) ---
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

    # --- Contato ---
    email = StringField(max_length=160, null=True)
    company = StringField(max_length=160, null=True)
    role = StringField(max_length=120, null=True)  # cargo
    contact_type = StringField(choices=tuple(domain.CONTACT_TYPES), default='lead')
    origin = StringField(choices=tuple(domain.ORIGINS), null=True)

    # --- Funil ---
    owner = StringField(choices=tuple(domain.OWNERS), default='sdr')
    human_operator = BooleanField(default=False)  # parceiro/cliente antigo: fica com a Erica, fora da fila da SDR
    product = StringField(choices=tuple(domain.PRODUCTS), null=True)
    qualification = DictField()  # todos os campos coletados (IA ou SDR), ver LeadQualificationService
    pending_fields = ListField(StringField())  # o que ficou "não sei"
    attachments = ListField(DictField())  # {url, kind, name, received_at}
    flags = ListField(StringField(choices=tuple(domain.FLAGS)))
    needs_erica = BooleanField(default=False)
    lost_reason = StringField(choices=tuple(domain.LOST_REASONS), null=True)
    next_action_at = DateTimeField(null=True)
    qualified_at = DateTimeField(null=True)
    first_contact_at = DateTimeField(null=True)
    stage_changed_at = DateTimeField(null=True)
    lead_number = IntField(default=1)  # quantos leads o contato já abriu (o atual incluso)
    lead_started_at = DateTimeField(null=True)  # início do lead atual (vazio = criação do contato)
    # Funil "zerado": só aparece quem entrou depois (atendido/qualificado pela IA ou lead aberto à mão).
    # Vazio = fora do funil (leads antigos). Ver crm.services.funnel_entry.
    funnel_entered_at = DateTimeField(null=True)
    ai_qualified_at = DateTimeField(null=True)  # a IA terminou a qualificação (cotação em WAITING_BUDGET)

    created_at = DateTimeField(default=datetime.utcnow)  # UTC sem fuso, como o resto do banco
    updated_at = DateTimeField(default=datetime.utcnow)

    def __str__(self) -> str:
        return f"{self.name or 'Sem Nome'} ({self.phone})"

    @property
    def stage(self) -> str:
        """Etapa no vocabulário novo, mesmo para registros ainda não migrados."""
        return domain.resolve_legacy_stage(self.customer_state_now, self.proposal_sent_at)

    def to_dict(self) -> dict:
        stage = self.stage
        return {
            "id": str(self.id),
            "name": self.name,
            "phone": self.phone,
            "agent": self.agent,
            "customer_state_now": stage,
            "actual_status": stage,
            "customer_custom_tag": self.customer_custom_tag,
            "celebration_type": self.celebration_type,
            "event_title": self.event_title,
            "event_date": _iso(self.event_date),
            "guest_count": self.guest_count,
            "quoted_amount": self.quoted_amount or 0,
            "contract_value": self.contract_value or 0,
            "venue": self.venue,
            "notes": self.notes,
            "proposal_sent_at": _iso(self.proposal_sent_at),
            "last_interaction_at": _iso(self.last_interaction_at),
            "next_step": self.next_step,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "new_service": self.new_service,
            "email": self.email,
            "company": self.company,
            "role": self.role,
            "contact_type": self.contact_type or 'lead',
            "origin": self.origin,
            "owner": self.owner or 'sdr',
            "human_operator": bool(self.human_operator),
            "product": self.product,
            "qualification": dict(self.qualification or {}),
            "pending_fields": list(self.pending_fields or []),
            "attachments": [
                {**a, "received_at": _iso(a.get("received_at")) if isinstance(a.get("received_at"), datetime) else a.get("received_at")}
                for a in (self.attachments or [])
            ],
            "flags": list(self.flags or []),
            "needs_erica": bool(self.needs_erica),
            "lost_reason": self.lost_reason,
            "next_action_at": _iso(self.next_action_at),
            "qualified_at": _iso(self.qualified_at),
            "first_contact_at": _iso(self.first_contact_at),
            "stage_changed_at": _iso(self.stage_changed_at),
            "lead_number": self.lead_number or 1,
            "lead_started_at": _iso(self.lead_started_at),
            "funnel_entered_at": _iso(self.funnel_entered_at),
            "ai_qualified_at": _iso(self.ai_qualified_at),
            "blocked_until": _iso(self.blocked_until),
            "silenced_until": _iso(self.silenced_until),
            "send_button": self.send_button,
            "waiting_for_name": self.waiting_for_name,
            "name_collected": self.name_collected,
            "last_message_attendant": _iso(self.last_message_attendant),
            "followup_sent": self.followup_sent,
        }
