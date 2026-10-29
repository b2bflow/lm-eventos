from mongoengine import CASCADE, NULLIFY, Document, ReferenceField, StringField, BooleanField, DateTimeField, IntField
from mongoengine.errors import DoesNotExist
from datetime import datetime
from crm.models.custumer_model import Customer
from crm.models.quote_model import Quote


class OptionalReferenceField(ReferenceField):
    """Referência que vira None quando o documento apontado já foi apagado. Um orçamento apagado
    sem limpar a conversa derrubava a lista inteira de conversas (erro 500). O próximo save da
    conversa grava o None."""

    def __get__(self, instance, owner):
        try:
            return super().__get__(instance, owner)
        except DoesNotExist:
            instance._data[self.name] = None
            instance._mark_as_changed(self.name)
            return None

class ConversationModel(Document):
    meta = {
        'collection': 'conversations',
        'strict': False
    }

    customer = ReferenceField(Customer, required=True, reverse_delete_rule=CASCADE)  # excluir o contato apaga as conversas
    quote = OptionalReferenceField(Quote, null=True, reverse_delete_rule=NULLIFY)
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
    # Hora da última mensagem trocada com o cliente (padrão WhatsApp): ordena a lista e aparece no card.
    # Abrir, ler, atribuir ou trocar IA/operador não mexe nela; notas e eventos internos também não.
    last_message_at = DateTimeField(null=True)
