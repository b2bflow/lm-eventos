from mongoengine import Document, ReferenceField, StringField, BooleanField, DateTimeField, IntField
from datetime import datetime
from crm.models.custumer_model import Customer

class ConversationModel(Document):
    meta = {
        'collection': 'conversations',
        'strict': False
    }

    customer = ReferenceField(Customer, required=True)
    status = StringField(choices=('OPEN', 'CLOSED', 'ARCHIVED'), default='OPEN')
    tag = StringField(default='OPERADOR')
    ai_active = BooleanField(default=False)
    needs_attention = BooleanField(default=False)
    final_customer_status = StringField()

    unread_count = IntField(default=0)
    last_message_content = StringField(default="")

    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)