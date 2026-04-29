from rest_framework import serializers

class CustomerDTO(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    phone = serializers.CharField()
    customer_state_now = serializers.CharField()
    actual_status = serializers.CharField(required=False)
    customer_custom_tag = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    celebration_type = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    event_title = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    event_date = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    guest_count = serializers.IntegerField(required=False)
    quoted_amount = serializers.FloatField(required=False)
    contract_value = serializers.FloatField(required=False)
    venue = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    notes = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    proposal_sent_at = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    last_interaction_at = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    next_step = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    created_at = serializers.CharField()
    updated_at = serializers.CharField()
    operator_name = serializers.SerializerMethodField()

    def _get_value(self, obj, key: str):
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    def get_operator_name(self, obj) -> str:
        from users.services.user_service import UserService
        try:
            op_id = self._get_value(obj, 'current_operator_id')
            if op_id:
                return UserService.get_user_name(op_id) or "Operador não encontrado"
            return "Não atribuído"
        except Exception:
            return "Erro ao buscar nome"


class QuoteDTO(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    quote_id = serializers.CharField(read_only=True)
    customer = serializers.CharField(read_only=True)
    customer_id = serializers.CharField(read_only=True)
    name = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    phone = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    customer_state_now = serializers.CharField()
    actual_status = serializers.CharField(required=False)
    status = serializers.CharField(required=False)
    customer_custom_tag = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    celebration_type = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    event_title = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    event_date = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    guest_count = serializers.IntegerField(required=False)
    quoted_amount = serializers.FloatField(required=False)
    contract_value = serializers.FloatField(required=False)
    venue = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    notes = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    proposal_sent_at = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    last_interaction_at = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    next_step = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    closed_at = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    created_at = serializers.CharField()
    updated_at = serializers.CharField()
