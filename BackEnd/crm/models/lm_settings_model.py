from datetime import datetime

from mongoengine import BooleanField, DateTimeField, DictField, Document, FloatField, IntField, ListField, StringField

# Seg=0 ... Dom=6. Cada dia: [abertura, fechamento] em "HH:MM" (horário de Brasília) ou None.
DEFAULT_BUSINESS_HOURS = {
    "0": ["08:00", "18:00"], "1": ["08:00", "18:00"], "2": ["08:00", "18:00"],
    "3": ["08:00", "18:00"], "4": ["08:00", "18:00"], "5": ["08:00", "12:00"], "6": None,
}

# Respostas rápidas da aba WhatsApp por produto ("geral" vale para todos). Escrita formal e sem
# emoji (regra 5). {nome} = primeiro nome do cliente; {sdr} = nome da SDR (sdr_name).
DEFAULT_QUICK_REPLIES = [
    {"product": "geral", "title": "Apresentação",
     "text": "Olá, {nome}. Aqui é {sdr}, da LM Eventos. Recebi o seu contato e vou dar continuidade ao seu atendimento."},
    {"product": "geral", "title": "Tentativa de ligação",
     "text": "Olá, {nome}. Tentei falar com você por telefone agora há pouco. Qual o melhor horário para conversarmos?"},
    {"product": "geral", "title": "Follow-up da proposta",
     "text": "Olá, {nome}. Gostaria de saber se conseguiu analisar a proposta que enviamos. Fico à disposição para esclarecer qualquer dúvida."},
    {"product": "geral", "title": "Proposta vencendo",
     "text": "Olá, {nome}. Lembramos que a proposta enviada é válida até amanhã. Podemos seguir com a reserva da data?"},
    {"product": "geral", "title": "Agendar reunião",
     "text": "Olá, {nome}. Para alinharmos os detalhes, podemos agendar uma reunião online com a Erica. Qual dia e horário ficam melhores para você?"},
    {"product": "estrutura_porta", "title": "Lista de peças",
     "text": "Para montarmos o orçamento da locação, poderia nos enviar a lista de peças ou uma foto da estrutura desejada?"},
    {"product": "estrutura_porta", "title": "Retirada e devolução",
     "text": "Poderia confirmar as datas de retirada e de devolução das peças? A locação padrão considera um final de semana."},
    {"product": "estrutura_montagem", "title": "Visita técnica",
     "text": "Para dimensionar a estrutura com segurança, a Erica pode realizar uma visita técnica no local. Qual o endereço e a melhor data?"},
    {"product": "corporativo", "title": "Detalhes do evento",
     "text": "Para concluirmos a proposta, poderia confirmar o número de participantes, o local e o horário de montagem?"},
    {"product": "corporativo", "title": "Rider técnico",
     "text": "Caso haja banda ou apresentação, poderia nos enviar o rider técnico para avaliarmos os equipamentos?"},
    {"product": "social", "title": "Pacote básico",
     "text": "Temos um pacote básico com estrutura, painel de LED, som, iluminação e DJ. Posso enviar os valores para a sua data?"},
    {"product": "produto_unico", "title": "Retirada ou entrega",
     "text": "O item pode ser retirado na LM sem custo adicional ou entregue no local com frete. Qual opção prefere?"},
]


class LmSettings(Document):
    """Configuração única da operação LM (coleção `lm_settings`, um documento).

    Valores ainda não validados com a Erica entram aqui com o padrão sugerido e podem ser
    editados sem deploy (ver seção 6 do documento de implementação).
    """

    meta = {'collection': 'lm_settings', 'strict': False}

    key = StringField(default='default', unique=True)

    business_hours = DictField(default=lambda: dict(DEFAULT_BUSINESS_HOURS))
    first_call_hour = StringField(default="09:00")  # fora do horário: ligar às 9h do próximo dia útil

    approval_ceiling = FloatField(default=15000.0)
    margin_levels = ListField(FloatField(), default=lambda: [0.20, 0.35, 0.50])
    invoice_rate = FloatField(default=0.15)
    proposal_validity_days = IntField(default=5)
    proposal_warning_day = IntField(default=4)
    call_sla_minutes = IntField(default=15)
    stale_lead_hours = IntField(default=24)
    # Cadência depois da proposta enviada (dias corridos a partir do envio).
    follow_up_days = DictField(default=lambda: {"follow_up_d1": 1, "follow_up_d3": 3, "follow_up_d5": 5})
    auto_lost_days = IntField(default=7)  # sem resposta: Perdido com motivo "sem resposta"
    reactivation_days = IntField(default=30)  # tarefa de reativação depois da perda automática
    max_guests_without_visit = IntField(default=1500)
    social_max_guests = IntField(default=200)  # social acima disso vira reunião com a Erica
    social_max_total = FloatField(default=6000.0)  # idem para o total

    # Reserva de estoque é opcional: desligada, proposta aceita não reserva peças e o
    # disponível passa a ser o total (reservas antigas ficam guardadas, só deixam de contar).
    inventory_reservations_enabled = BooleanField(default=True)

    # Tabela de preços e custos operacionais da calculadora (padrões em sales/pricing.py).
    price_table = DictField()

    # Contatos para avisos por WhatsApp (telefone com DDI ou id de grupo da Z-API).
    approval_phone = StringField(default="")
    erica_phone = StringField(default="")
    sdr_phone = StringField(default="")
    lucia_phone = StringField(default="")
    # Grupo de atendimento (Marcelo e Erica): aviso a cada lead qualificado pela IA. Id de grupo da Z-API.
    ai_leads_group = StringField(default="")
    sdr_name = StringField(default="")
    dj_partner_contact = StringField(default="")
    job_link = StringField(default="")
    quick_replies = ListField(DictField(), default=lambda: [dict(r) for r in DEFAULT_QUICK_REPLIES])
    # Textos do PDF da proposta
    payment_terms_text = StringField(default="Forma de pagamento: a combinar.")
    down_payment_text = StringField(default="Sinal: a combinar.")
    cancellation_text = StringField(default="Condições de cancelamento: a combinar.")

    google_refresh_token = StringField(default="")
    google_calendar_id = StringField(default="")
    google_sync_token = StringField(default="")
    google_auto_sync = BooleanField(default=True)  # beat lê o Google a cada 10 min; desligado = só pelo botão
    google_last_sync_at = DateTimeField(null=True)

    updated_at = DateTimeField(default=datetime.utcnow)

    # Campos que nunca saem pela API
    SECRET_FIELDS = ("google_refresh_token", "google_sync_token")

    @classmethod
    def get(cls) -> "LmSettings":
        settings = cls.objects(key='default').first()
        if not settings:
            settings = cls(key='default').save()
        return settings

    def to_dict(self) -> dict:
        data = self.to_mongo().to_dict()
        data.pop("_id", None)
        for field in self.SECRET_FIELDS:
            data.pop(field, None)
        data["google_connected"] = bool(self.google_refresh_token)
        for field in ("updated_at", "google_last_sync_at"):
            if isinstance(data.get(field), datetime):
                data[field] = data[field].isoformat()
        return data
