from mongoengine import NULLIFY, Document, ReferenceField, StringField, BooleanField, DateTimeField, IntField
from datetime import datetime
from crm.models.custumer_model import Customer
from crm.models.quote_model import Quote

class ConversationModel(Document):
    meta = {
        'collection': 'conversations',
        'strict': False
    }

    customer = ReferenceField(Customer, required=True)
    quote = ReferenceField(Quote, null=True, reverse_delete_rule=NULLIFY)
    status = StringField(choices=('OPEN', 'CLOSED', 'ARCHIVED'), default='OPEN')
    tag = StringField(default='OPERADOR')
    ai_active = BooleanField(default=False)
    needs_attention = BooleanField(default=False)
    final_customer_status = StringField()

    unread_count = IntField(default=0)
    last_message_content = StringField(default="")

    # Responsável pela conversa na equipe (independe do responsável do lead no funil).
    assignee = StringField(choices=('sdr', 'erica', 'lucia'), null=True)
    # Última passagem entre IA e humano: quem fez e quando (ver ConversationHandoverService).
    handover_by = StringField(null=True)  # id do usuário Django
    handover_at = DateTimeField(null=True)

    created_at = DateTimeField(default=datetime.utcnow)  # UTC sem fuso, como o resto do banco
    updated_at = DateTimeField(default=datetime.utcnow)
