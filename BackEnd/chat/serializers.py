from rest_framework import serializers
from rest_framework_mongoengine.serializers import DocumentSerializer
from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel

class ConversationSerializer(DocumentSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True, default="Desconhecido")
    customer_phone = serializers.CharField(source='customer.phone', read_only=True, default="Sem Número")
    customer_status = serializers.CharField(source='customer.customer_state_now', read_only=True, default="ANALYSIS")
    customer_custom_tag = serializers.CharField(source='customer.customer_custom_tag', read_only=True, allow_null=True)
    blocked_until = serializers.DateTimeField(source='customer.blocked_until', read_only=True, allow_null=True)
    quote_id = serializers.CharField(source='quote.id', read_only=True, allow_null=True)
    customer_state_now = serializers.CharField(source='quote.status', read_only=True, allow_null=True)
    celebration_type = serializers.CharField(source='quote.celebration_type', read_only=True, allow_null=True)
    event_title = serializers.CharField(source='quote.event_title', read_only=True, allow_null=True)
    event_date = serializers.DateTimeField(source='quote.event_date', read_only=True, allow_null=True)
    event_time = serializers.CharField(source='quote.event_time', read_only=True, allow_null=True)
    guest_count = serializers.IntegerField(source='quote.guest_count', read_only=True, allow_null=True)
    quoted_amount = serializers.FloatField(source='quote.quoted_amount', read_only=True, allow_null=True)
    contract_value = serializers.FloatField(source='quote.contract_value', read_only=True, allow_null=True)
    venue = serializers.CharField(source='quote.venue', read_only=True, allow_null=True)
    notes = serializers.CharField(source='quote.notes', read_only=True, allow_null=True)
    operator_requests = serializers.CharField(source='quote.operator_requests', read_only=True, allow_null=True)
    next_step = serializers.CharField(source='quote.next_step', read_only=True, allow_null=True)
    
    last_interaction_at = serializers.DateTimeField(source='updated_at', read_only=True)
    past_conversations = serializers.SerializerMethodField()
    past_quotes = serializers.SerializerMethodField()
    final_customer_status = serializers.CharField(read_only=True)
    needs_attention = serializers.BooleanField(read_only=True) 
    customer_product = serializers.CharField(source='customer.product', read_only=True, default=None)
    customer_human_operator = serializers.BooleanField(source='customer.human_operator', read_only=True, default=False)
    handover_by_name = serializers.SerializerMethodField()
    

    class Meta:
        model = ConversationModel
        fields = [
            'id', 'customer', 'quote_id', 'customer_name', 'customer_phone', 'customer_status', 
            'customer_custom_tag',
            'customer_state_now', 'celebration_type', 'event_title', 'event_date', 'event_time',
            'guest_count', 'quoted_amount', 'contract_value', 'venue', 'notes',
            'operator_requests', 'next_step',
            'status', 'tag', 'ai_active', 'last_message_content', 
            'last_interaction_at', 'unread_count', 'created_at',
            'final_customer_status', 'past_conversations', 'past_quotes',
            'needs_attention', 'blocked_until', 'assignee', 'handover_by', 'handover_by_name', 'handover_at',
            'customer_product', 'customer_human_operator',
        ]

    def get_handover_by_name(self, obj):
        """Nome de quem retomou a IA ou assumiu a conversa por último."""
        user_id = getattr(obj, 'handover_by', None)
        if not user_id:
            return None
        from chat.services.handover_service import user_display_name
        from users.models.user_model import User
        user = User.objects.filter(id=user_id).first() if str(user_id).isdigit() else None
        return user_display_name(user) if user else None

    def get_past_conversations(self, obj):
        try:
            past = ConversationModel.objects(customer=obj.customer, id__ne=obj.id).only('id', 'created_at', 'status', 'final_customer_status', 'customer').order_by('-created_at')
            return [
                {
                    "id": str(c.id),
                    "created_at": c.created_at.isoformat(),
                    "status": c.status,
                    "final_customer_status": getattr(c, 'final_customer_status', getattr(c.customer, 'customer_state_now', 'ANALYSIS'))
                } for c in past
            ]
        except Exception:
            return []

    def get_past_quotes(self, obj):
        try:
            from crm.models.quote_model import Quote
            current_quote_id = str(obj.quote.id) if getattr(obj, "quote", None) else None
            quotes = Quote.objects(customer=obj.customer).order_by('-created_at')
            return [
                quote.to_dict()
                for quote in quotes
                if not current_quote_id or str(quote.id) != current_quote_id
            ]
        except Exception:
            return []

class MessageSerializer(DocumentSerializer):
    conversation_id = serializers.CharField(source='conversation.id', read_only=True)
    buttons = serializers.SerializerMethodField()
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = MessageModel
        fields = [
            'id', 'conversation_id', 'role', 'direction', 
            'status', 'message_type', 'content', 'media_url', 'raw_metadata', 'buttons', 'author_name', 'created_at'
        ]

    def get_author_name(self, obj):
        """Quem escreveu a nota interna ou fez a ação (mensagens INTERNAL)."""
        if getattr(obj, 'direction', None) != 'INTERNAL':
            return None
        return (getattr(obj, 'raw_metadata', None) or {}).get('operator_name')

    def get_buttons(self, obj):
        """Botões enviados no menu (só para exibição no painel)."""
        buttons = (getattr(obj, 'raw_metadata', None) or {}).get('buttons')
        return buttons if isinstance(buttons, list) else None


SECRET_MASK = "••••"


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    return f"{SECRET_MASK}{value[-4:]}" if len(value) > 4 else SECRET_MASK


class SystemConfigDTO(serializers.Serializer):
    """Configurações globais. Segredos saem mascarados; o front reenvia o valor mascarado sem alterar."""
    webhook_token = serializers.SerializerMethodField()
    zapi_instance_id = serializers.CharField(allow_blank=True, required=False)
    zapi_token = serializers.SerializerMethodField()
    openai_api_key = serializers.SerializerMethodField()
    ai_active = serializers.BooleanField(required=False)

    def get_webhook_token(self, obj) -> str:
        return mask_secret(getattr(obj, 'webhook_token', ''))

    def get_zapi_token(self, obj) -> str:
        return mask_secret(getattr(obj, 'zapi_token', ''))

    def get_openai_api_key(self, obj) -> str:
        return mask_secret(getattr(obj, 'openai_api_key', ''))
