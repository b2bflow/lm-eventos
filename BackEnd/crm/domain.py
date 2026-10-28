"""Vocabulário do funil comercial da LM (etapas, transições e listas de valores do card).

Fonte única para models, serviços, endpoints e testes. O frontend espelha os rótulos em
FrontEnd/src/constants/mappings.ts.
"""

# --- Etapas -----------------------------------------------------------------------------
NEW_LEAD = 'NEW_LEAD'
QUALIFIED = 'QUALIFIED'
MEETING_SCHEDULED = 'MEETING_SCHEDULED'
PROPOSAL_SENT = 'PROPOSAL_SENT'
PROPOSAL_ACCEPTED = 'PROPOSAL_ACCEPTED'
CONTRACT_SIGNED = 'CONTRACT_SIGNED'
LOST = 'LOST'

STAGES = (NEW_LEAD, QUALIFIED, MEETING_SCHEDULED, PROPOSAL_SENT, PROPOSAL_ACCEPTED, CONTRACT_SIGNED, LOST)

# Colunas do quadro. "Novo lead" saiu (reunião com o Marcelo, 28/10): o funil começa em "Lead
# qualificado" (IA qualificou ou alguém abriu o lead à mão). NEW_LEAD segue como etapa do contato
# que ainda não é lead do funil.
BOARD_STAGES = tuple(s for s in STAGES if s != NEW_LEAD)

STAGE_LABELS = {
    NEW_LEAD: 'Novo lead',
    QUALIFIED: 'Lead qualificado',
    MEETING_SCHEDULED: 'Reunião agendada',
    PROPOSAL_SENT: 'Proposta enviada',
    PROPOSAL_ACCEPTED: 'Proposta aceita',
    CONTRACT_SIGNED: 'Contrato assinado',
    LOST: 'Perdido',
}

# Etapas do processo antigo. Continuam aceitas no banco até o `migrate_lm_stages` rodar,
# mas nunca são gravadas pelo código novo e saem traduzidas nas leituras.
LEGACY_STAGES = ('ANALYSIS', 'BUDGET', 'WAITING_BUDGET', 'NEGOTIATING', 'WON')


def resolve_legacy_stage(stage: str | None, proposal_sent_at=None) -> str:
    """Etapa nova equivalente a uma etapa antiga (regra do migrate_lm_stages)."""
    if stage in STAGES:
        return stage
    if stage == 'WAITING_BUDGET':
        return QUALIFIED
    if stage == 'BUDGET':
        return PROPOSAL_SENT if proposal_sent_at else QUALIFIED
    if stage == 'NEGOTIATING':
        return PROPOSAL_SENT
    if stage == 'WON':
        return CONTRACT_SIGNED
    return NEW_LEAD


# Transições do card / Kanban: livres entre as colunas do quadro (reunião com o Marcelo, 28/10).
TRANSITIONS = {stage: set(BOARD_STAGES) - {stage} for stage in STAGES}

# --- Listas do card -------------------------------------------------------------------
PRODUCTS = {
    'estrutura_porta': 'Estrutura (locação de porta)',
    'estrutura_montagem': 'Estrutura com montagem',
    'corporativo': 'Evento corporativo',
    'social': 'Evento social',
    'produto_unico': 'Produto único',
}

OWNERS = {'sdr': 'SDR', 'erica': 'Erica', 'lucia': 'Lúcia'}

CONTACT_TYPES = {
    'lead': 'Lead', 'cliente': 'Cliente', 'parceiro': 'Parceiro',
    'fornecedor': 'Fornecedor', 'candidato': 'Candidato', 'outro': 'Outro',
}

ORIGINS = {
    'anuncio_ctwa': 'Anúncio (clique para WhatsApp)', 'instagram': 'Instagram', 'google': 'Google',
    'indicacao': 'Indicação', 'site': 'Site', 'parceiro': 'Parceiro',
}

FLAGS = {
    'ligacao_pendente': 'Ligação pendente',
    'reuniao_agendada': 'Reunião agendada',
    'visita_agendada': 'Visita agendada',
    'aguardando_erica': 'Aguardando Erica',
    'aguardando_cliente': 'Aguardando cliente',
    'aguardando_aprovacao_desconto': 'Aguardando aprovação',
}

LOST_REASONS = {
    'preco': 'Preço',
    'data_indisponivel': 'Data indisponível',
    'sem_resposta': 'Sem resposta',
    'fechou_com_outro': 'Fechou com outro',
    'desistiu': 'Desistiu',
}

ATTACHMENT_KINDS = {
    'rider': 'Rider técnico',
    'projeto': 'Projeto',
    'orcamento_concorrente': 'Orçamento concorrente',
    'lista_pecas': 'Lista de peças',
    'outro': 'Outro',
}
