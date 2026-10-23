"""Funil comercial: transições de etapa explícitas, sinalizações, próxima ação, notas, ligações
e o quadro agrupado por etapa (paginado no banco)."""
from datetime import datetime

from bson import ObjectId
from mongoengine.queryset.visitor import Q

from crm import domain
from crm.models.custumer_model import Customer
from crm.models.log_service_model import ServiceLog
from crm.repositories.log_service_repository import ServiceLogRepository
from users.permissions import ADMIN, PORTA, user_role

CALL_OUTCOMES = {
    'atendeu': 'Atendeu',
    'nao_atendeu': 'Não atendeu',
    'caixa_postal': 'Caixa postal',
    'numero_invalido': 'Número inválido',
    'remarcar': 'Pediu para ligar depois',
}


def _operator_id(user) -> str | None:
    return str(user.id) if user is not None and getattr(user, 'id', None) else None


def _get_document(customer_id: str) -> Customer:
    try:
        customer = Customer.objects(id=ObjectId(customer_id)).first()
    except Exception:
        customer = None
    if not customer:
        raise ValueError("Lead não encontrado.")
    return customer


class PermissionDeniedError(Exception):
    """Ação não permitida para o papel do usuário."""


class PipelineService:

    # --- Etapas ------------------------------------------------------------------------

    def validate_transition(self, customer: dict | Customer, target: str, user=None, lost_reason: str | None = None) -> None:
        current = customer['customer_state_now'] if isinstance(customer, dict) else customer.stage
        product = customer.get('product') if isinstance(customer, dict) else customer.product
        proposal_sent_at = customer.get('proposal_sent_at') if isinstance(customer, dict) else customer.proposal_sent_at

        if target not in domain.STAGES:
            raise ValueError(f"Etapa inválida: {target}.")
        if target == current:
            return
        if target not in domain.TRANSITIONS.get(current, set()):
            raise ValueError(
                f"Não é possível mover de '{domain.STAGE_LABELS[current]}' para '{domain.STAGE_LABELS[target]}'."
            )
        if target == domain.LOST and lost_reason not in domain.LOST_REASONS:
            raise ValueError("Informe o motivo da perda.")
        if target == domain.PROPOSAL_SENT and not proposal_sent_at:
            raise ValueError("Envie a proposta pela calculadora para mover o lead para 'Proposta enviada'.")
        if target == domain.PROPOSAL_ACCEPTED and not self.latest_sent_proposal(customer):
            raise ValueError("Não há proposta enviada válida para aceitar. Envie a proposta (ou uma nova versão, "
                             "se a anterior venceu) antes de mover para 'Proposta aceita'.")
        if user is not None:
            if target == domain.CONTRACT_SIGNED:
                # Lúcia fecha a locação de porta; eventos ficam com a Erica (admin).
                allowed = user_role(user) == ADMIN or (user_role(user) == PORTA and product == 'estrutura_porta')
                if not allowed:
                    raise PermissionDeniedError("Só a Erica (eventos) ou a Lúcia (locação de porta) registram contrato assinado.")

    @staticmethod
    def latest_sent_proposal(customer):
        """Última proposta enviada (e ainda não vencida) do lead atual, ou None."""
        from sales.models import Proposal
        customer_id = customer['id'] if isinstance(customer, dict) else customer.id
        return Proposal.objects(customer=customer_id, opportunity_id=None, status='enviada').order_by('-version').first()

    def change_stage(self, customer_id: str, target: str, user=None, lost_reason: str | None = None,
                     note: str | None = None, system: bool = False) -> dict:
        """Muda a etapa validando a transição. `system=True` é usado pelos fluxos automáticos
        (qualificação, envio e aceite de proposta), que já garantem a pré-condição.

        Mover para 'Proposta aceita' pelo card aceita a última proposta enviada (reserva o estoque e
        avisa a Lúcia na locação de porta). Sair de 'Proposta aceita' para trás ou para 'Perdido'
        desfaz o aceite e libera o estoque reservado."""
        customer = _get_document(customer_id)
        previous = customer.stage
        if not system:
            self.validate_transition(customer, target, user, lost_reason)
        elif target not in domain.STAGES:
            raise ValueError(f"Etapa inválida: {target}.")
        if previous == target and customer.customer_state_now == target:
            return customer.to_dict()
        if not system and target == domain.PROPOSAL_ACCEPTED:
            from sales.services.proposal_service import ProposalService
            ProposalService().accept(str(self.latest_sent_proposal(customer).id), user=user, note=note)
            return _get_document(customer_id).to_dict()

        now = datetime.utcnow()
        customer.customer_state_now = target
        customer.stage_changed_at = now
        customer.updated_at = now
        if target == domain.LOST:
            customer.lost_reason = lost_reason
            customer.next_action_at = None
        elif previous == domain.LOST:
            customer.lost_reason = None
        customer.save()

        undo_acceptance = (previous == domain.PROPOSAL_ACCEPTED and target in (domain.PROPOSAL_SENT, domain.LOST)) or (
            previous == domain.CONTRACT_SIGNED and target == domain.LOST)
        if undo_acceptance:
            from sales.services.proposal_service import ProposalService
            ProposalService().undo_acceptance(customer, back_to_sent=target == domain.PROPOSAL_SENT, user=user)
            customer.reload()  # o valor do card pode ter voltado para o da última proposta enviada

        if target == domain.LOST:
            from crm.container import CrmContainer
            CrmContainer.get_sdr_task_service().cancel_pending_for_customer(customer_id)
        elif previous == domain.PROPOSAL_SENT:
            from crm.container import CrmContainer
            CrmContainer.get_sdr_task_service().cancel_cadence(customer_id)

        description = f"Etapa: {domain.STAGE_LABELS[previous]} -> {domain.STAGE_LABELS[target]}."
        if target == domain.LOST:
            description += f" Motivo: {domain.LOST_REASONS[lost_reason]}."
        if note:
            description += f" {note}"
        ServiceLogRepository.create_log(
            customer=customer, operator_id=_operator_id(user), action_type='STAGE_CHANGED',
            description=description,
            metadata={"from": previous, "to": target, "lost_reason": lost_reason, "system": system},
        )
        return customer.to_dict()

    # --- Card ---------------------------------------------------------------------------

    def set_flags(self, customer_id: str, add: list[str] | None = None, remove: list[str] | None = None, user=None) -> dict:
        add, remove = list(add or []), list(remove or [])
        invalid = [f for f in add + remove if f not in domain.FLAGS]
        if invalid:
            raise ValueError(f"Sinalização inválida: {', '.join(invalid)}.")
        customer = _get_document(customer_id)
        flags = [f for f in (customer.flags or []) if f not in remove]
        flags += [f for f in add if f not in flags]
        if flags == list(customer.flags or []):
            return customer.to_dict()
        customer.flags = flags
        customer.needs_erica = customer.needs_erica or 'aguardando_erica' in add
        customer.updated_at = datetime.utcnow()
        customer.save()
        labels = ", ".join(domain.FLAGS[f] for f in flags) or "nenhuma"
        ServiceLogRepository.create_log(
            customer=customer, operator_id=_operator_id(user), action_type='FLAGS_CHANGED',
            description=f"Sinalizações: {labels}.", metadata={"added": add, "removed": remove},
        )
        return customer.to_dict()

    def set_next_action(self, customer_id: str, next_step: str | None, next_action_at: datetime | None, user=None) -> dict:
        customer = _get_document(customer_id)
        customer.next_step = (next_step or "").strip()[:160] or None
        customer.next_action_at = next_action_at
        customer.updated_at = datetime.utcnow()
        customer.save()
        when = next_action_at.strftime('%d/%m/%Y %H:%M') + " (UTC)" if next_action_at else "sem data"
        ServiceLogRepository.create_log(
            customer=customer, operator_id=_operator_id(user), action_type='NEXT_ACTION_SET',
            description=f"Próxima ação: {customer.next_step or 'nenhuma'} ({when}).",
            metadata={"next_step": customer.next_step, "next_action_at": next_action_at.isoformat() if next_action_at else None},
        )
        return customer.to_dict()

    def add_note(self, customer_id: str, text: str, user=None) -> dict:
        text = (text or "").strip()
        if not text:
            raise ValueError("A nota não pode ficar vazia.")
        customer = _get_document(customer_id)
        log = ServiceLogRepository.create_log(
            customer=customer, operator_id=_operator_id(user), action_type='NOTE_ADDED', description=text,
        )
        return log.to_dict()

    def log_call(self, customer_id: str, outcome: str, notes: str | None = None, user=None) -> dict:
        if outcome not in CALL_OUTCOMES:
            raise ValueError("Resultado da ligação inválido.")
        customer = _get_document(customer_id)
        now = datetime.utcnow()
        if outcome == 'atendeu' and not customer.first_contact_at:
            customer.first_contact_at = now
        customer.last_interaction_at = now
        if outcome == 'atendeu' and 'ligacao_pendente' in (customer.flags or []):
            customer.flags = [f for f in customer.flags if f != 'ligacao_pendente']
        customer.updated_at = now
        customer.save()

        description = f"Ligação: {CALL_OUTCOMES[outcome]}."
        if notes:
            description += f" {notes.strip()}"
        log = ServiceLogRepository.create_log(
            customer=customer, operator_id=_operator_id(user), action_type='CALL_LOGGED',
            description=description, metadata={"outcome": outcome},
        )
        if outcome == 'atendeu':
            from crm.container import CrmContainer
            CrmContainer.get_sdr_task_service().complete_pending(
                customer_id, ['ligar_15min', 'retomar_lead_parado', 'follow_up_d1', 'follow_up_d5'], user=user
            )
        return log.to_dict()

    def remove_from_funnel(self, customer_id: str, user=None) -> dict:
        """Tira o card do quadro (limpa `funnel_entered_at`) sem apagar nada: contato, conversa,
        propostas e histórico continuam na página Contatos. Volta ao funil pelos caminhos de
        crm.services.funnel_entry (Abrir lead, proposta salva, qualificação da IA)."""
        customer = _get_document(customer_id)
        if customer.funnel_entered_at is None:
            raise ValueError("Este lead já está fora do funil.")
        if customer.stage in (domain.PROPOSAL_ACCEPTED, domain.CONTRACT_SIGNED):
            raise ValueError("Lead com proposta aceita ou contrato assinado não sai do funil: "
                             "marque como perdido antes, para liberar o estoque reservado.")
        customer.funnel_entered_at = None
        customer.next_action_at = None
        customer.updated_at = datetime.utcnow()
        customer.save()
        from crm.container import CrmContainer
        CrmContainer.get_sdr_task_service().cancel_pending_for_customer(customer_id)
        ServiceLogRepository.create_log(
            customer=customer, operator_id=_operator_id(user), action_type='FUNNEL_REMOVED',
            description=f"Card excluído do funil (etapa {domain.STAGE_LABELS[customer.stage]}).",
            metadata={"stage": customer.stage},
        )
        return customer.to_dict()

    def timeline(self, customer_id: str, limit: int = 200) -> list[dict]:
        _get_document(customer_id)
        # Só o lead atual; leads arquivados aparecem na página Contatos.
        logs = ServiceLog.objects(customer=customer_id, opportunity_id=None).order_by('-created_at').limit(limit)
        return [log.to_dict() for log in logs]

    # --- Quadro -------------------------------------------------------------------------

    def _board_queryset(self, product=None, owner=None, flag=None, search=None, include_human=False,
                        ai_qualified=False):
        # Só quem entrou no funil depois de zerado (crm.services.funnel_entry)
        queryset = Customer.objects(contact_type__nin=['parceiro', 'fornecedor', 'candidato'], funnel_entered_at__ne=None)
        if not include_human:
            queryset = queryset.filter(human_operator__ne=True)
        if ai_qualified:
            queryset = queryset.filter(ai_qualified_at__ne=None)
        if product:
            queryset = queryset.filter(product=product)
        if owner:
            queryset = queryset.filter(owner=owner)
        if flag:
            queryset = queryset.filter(flags=flag)
        if search:
            term = search.strip()
            queryset = queryset.filter(Q(name__icontains=term) | Q(phone__icontains=term) | Q(company__icontains=term))
        return queryset

    # Etapas antigas ainda não migradas aparecem na coluna equivalente.
    _STAGE_SOURCES = {
        domain.NEW_LEAD: [domain.NEW_LEAD, 'ANALYSIS'],
        domain.QUALIFIED: [domain.QUALIFIED],
        domain.PROPOSAL_SENT: [domain.PROPOSAL_SENT, 'NEGOTIATING'],
        domain.PROPOSAL_ACCEPTED: [domain.PROPOSAL_ACCEPTED],
        domain.CONTRACT_SIGNED: [domain.CONTRACT_SIGNED, 'WON'],
        domain.LOST: [domain.LOST],
    }

    def _stage_queryset(self, base, stage: str):
        sources = list(self._STAGE_SOURCES[stage])
        if stage == domain.QUALIFIED:
            return base.filter(Q(customer_state_now=domain.QUALIFIED) | (Q(customer_state_now='BUDGET') & Q(proposal_sent_at=None)))
        if stage == domain.PROPOSAL_SENT:
            return base.filter(Q(customer_state_now__in=sources) | (Q(customer_state_now='BUDGET') & Q(proposal_sent_at__ne=None)))
        return base.filter(customer_state_now__in=sources)

    @staticmethod
    def _cards(customers: list[Customer]) -> list[dict]:
        """Cards do funil com a proposta atual do lead (última versão), que aparece anexada no card."""
        from sales.models import STATUS_LABELS, Proposal
        from sales.services.proposal_pdf import file_name

        latest = {}
        if customers:
            proposals = (Proposal.objects(customer__in=[c.id for c in customers], opportunity_id=None,
                                          status__ne='substituida')
                         .no_dereference().only('id', 'customer', 'version', 'mode', 'status', 'total')
                         .order_by('-version'))
            for p in proposals:
                latest.setdefault(str(getattr(p.customer, 'id', p.customer)), p)
        cards = []
        for customer in customers:
            card = customer.to_dict()
            p = latest.get(str(customer.id))
            card["current_proposal"] = p and {
                "id": str(p.id), "version": p.version, "mode": p.mode, "status": p.status,
                "status_label": STATUS_LABELS.get(p.status, p.status), "total": p.total,
                "file_name": file_name({"client_name": customer.name or customer.company or "Cliente",
                                        "version": p.version}),
            }
            cards.append(card)
        return cards

    def lead_list(self, offset: int = 0, limit: int = 50, stage: str | None = None, **filters) -> dict:
        """Funil em lista: os mesmos leads e filtros do quadro, numa lista só, paginada no banco."""
        base = self._board_queryset(**filters)
        queryset = self._stage_queryset(base, stage) if stage else base
        offset = max(int(offset or 0), 0)
        total = queryset.count()
        items = list(queryset.order_by('-updated_at', '-id').skip(offset).limit(limit))
        return {"count": total, "offset": offset, "has_more": offset + len(items) < total,
                "results": self._cards(items)}

    def board(self, stages: list[str] | None = None, per_stage: int = 30, offsets: dict | None = None, **filters) -> dict:
        """Colunas do funil: {stage: {count, results, offset, has_more}}. Cada coluna paginada no banco."""
        offsets = offsets or {}
        columns = {}
        base = self._board_queryset(**filters)
        for stage in stages or domain.STAGES:
            queryset = self._stage_queryset(base, stage)
            offset = int(offsets.get(stage, 0) or 0)
            total = queryset.count()
            items = list(queryset.order_by('-updated_at', '-id').skip(offset).limit(per_stage))
            columns[stage] = {
                "label": domain.STAGE_LABELS[stage],
                "count": total,
                "offset": offset,
                "has_more": offset + len(items) < total,
                "results": self._cards(items),
            }
        return columns
