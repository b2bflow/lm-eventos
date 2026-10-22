"""Contatos: um contato (telefone único) com vários leads ao longo do tempo.

O lead em andamento fica no próprio Customer; os encerrados ficam em `opportunities`
(ver crm.models.opportunity_model). Também importa a lista de parceiros da Erica (CSV).
"""
import csv
import io
import unicodedata
from datetime import datetime

from bson import ObjectId
from mongoengine.queryset.visitor import Q

from crm import domain
from crm.models.custumer_model import Customer
from crm.models.log_service_model import ServiceLog
from crm.models.opportunity_model import LEAD_FIELDS, Opportunity
from crm.models.sdr_task_model import SdrTask
from crm.phones import normalize_phone, phone_variants
from crm.repositories.log_service_repository import ServiceLogRepository

CLOSED_STAGES = (domain.CONTRACT_SIGNED, domain.LOST)

# Campos do contato editáveis na página Contatos (os do lead ficam no card do funil).
CONTACT_FIELDS = ("name", "email", "company", "role", "contact_type", "origin", "owner", "notes")

# Estado de um lead novo no Customer (o que não está aqui é do contato e fica).
EMPTY_LEAD = {
    "product": None, "lost_reason": None, "qualification": {}, "pending_fields": [], "attachments": [],
    "flags": [], "quoted_amount": 0, "contract_value": 0, "event_date": None, "event_title": None,
    "celebration_type": None, "guest_count": 0, "venue": None, "needs_erica": False, "qualified_at": None,
    "first_contact_at": None, "proposal_sent_at": None, "next_step": None, "next_action_at": None,
    "ai_qualified_at": None,
}

PHONE_HEADERS = {"telefone", "phone", "celular", "numero", "whatsapp", "fone", "contato_telefone"}
NAME_HEADERS = {"nome", "name", "contato", "parceiro", "empresa"}
MAX_IMPORT_ROWS = 5000


class DuplicateContactError(ValueError):
    def __init__(self, existing: Customer):
        super().__init__(f"Já existe um contato com este telefone: {existing.name or existing.phone}.")
        self.existing_id = str(existing.id)


def _operator(user) -> str | None:
    return str(user.id) if user is not None and getattr(user, "id", None) else None


def _get(customer_id: str) -> Customer:
    try:
        customer = Customer.objects(id=ObjectId(customer_id)).first()
    except Exception:
        customer = None
    if not customer:
        raise ValueError("Contato não encontrado.")
    return customer


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return text.strip().lower().replace(" ", "_")


def find_by_phone(phone: str) -> Customer | None:
    return Customer.objects(phone__in=phone_variants(phone)).order_by("created_at").first()


def has_current_lead(customer: Customer) -> bool:
    """O contato tem um lead atual (dados de lead no Customer), esteja ele no funil ou não."""
    if customer.product:
        return True
    return not customer.human_operator and (customer.contact_type or "lead") not in ("parceiro", "fornecedor", "candidato")


def in_funnel(customer: Customer) -> bool:
    """O lead atual aparece no quadro do funil (mesma regra de PipelineService._board_queryset).

    Leads de antes do funil zerado (sem funnel_entered_at) continuam no histórico do contato, mas
    não estão no funil: dá para abrir um lead novo para eles.
    """
    return (customer.funnel_entered_at is not None and has_current_lead(customer)
            and (customer.contact_type or "lead") not in ("parceiro", "fornecedor", "candidato"))


class ContactService:

    # --- Leitura ---------------------------------------------------------------------------

    def _queryset(self, search=None, contact_type=None, owner=None, partner=None):
        queryset = Customer.objects
        if contact_type:
            queryset = queryset.filter(contact_type=contact_type)
        if owner:
            queryset = queryset.filter(owner=owner)
        if partner is True:
            queryset = queryset.filter(human_operator=True)
        elif partner is False:
            queryset = queryset.filter(human_operator__ne=True)
        term = (search or "").strip()
        if term:
            condition = Q(name__icontains=term) | Q(company__icontains=term) | Q(email__icontains=term)
            digits = "".join(ch for ch in term if ch.isdigit())
            if len(digits) >= 4:
                condition = condition | Q(phone__contains=digits)
            queryset = queryset.filter(condition)
        return queryset

    def list_contacts(self, offset: int = 0, limit: int = 30, **filters) -> tuple[list[dict], int]:
        queryset = self._queryset(**filters)
        total = queryset.count()
        customers = list(queryset.order_by("-updated_at", "-id").skip(offset).limit(limit))
        archived: dict[str, int] = {}
        for opp in Opportunity.objects(customer__in=[c.id for c in customers]).only("customer"):
            key = str(opp.customer.id)
            archived[key] = archived.get(key, 0) + 1
        return [self._summary(c, archived.get(str(c.id), 0)) for c in customers], total

    @staticmethod
    def _contact_fields(customer: Customer) -> dict:
        return {
            "id": str(customer.id),
            "name": customer.name,
            "phone": customer.phone,
            "email": customer.email,
            "company": customer.company,
            "role": customer.role,
            "contact_type": customer.contact_type or "lead",
            "origin": customer.origin,
            "owner": customer.owner or "sdr",
            "human_operator": bool(customer.human_operator),
            "notes": customer.notes,
            "last_interaction_at": customer.last_interaction_at.isoformat() if customer.last_interaction_at else None,
            "created_at": customer.created_at.isoformat() if customer.created_at else None,
            "updated_at": customer.updated_at.isoformat() if customer.updated_at else None,
        }

    def _summary(self, customer: Customer, archived_count: int) -> dict:
        current = has_current_lead(customer)
        return {
            **self._contact_fields(customer),
            "current_lead": {"stage": customer.stage, "product": customer.product} if current else None,
            "leads_count": archived_count + (1 if current else 0),
        }

    @staticmethod
    def _current_lead(customer: Customer) -> dict:
        data = customer.to_dict()
        return {
            "id": "current",
            "number": customer.lead_number or 1,
            "current": True,
            "stage": data["customer_state_now"],
            **{key: data.get(key) for key in (
                "product", "lost_reason", "qualification", "pending_fields", "attachments", "flags",
                "quoted_amount", "contract_value", "event_date", "event_title", "celebration_type",
                "guest_count", "venue", "owner", "qualified_at", "proposal_sent_at",
            )},
            "started_at": data["lead_started_at"] or data["created_at"],
            "closed_at": data["stage_changed_at"] if data["customer_state_now"] in CLOSED_STAGES else None,
        }

    def detail(self, customer_id: str) -> dict:
        """Contato + histórico de leads (o atual primeiro), propostas de cada lead e anexos."""
        from chat.models.conversation_model import ConversationModel
        from sales.models import STATUS_LABELS, Proposal

        customer = _get(customer_id)
        leads = [o.to_dict() for o in Opportunity.objects(customer=customer).order_by("-number")]
        if has_current_lead(customer):
            leads.insert(0, self._current_lead(customer))
        proposals: dict[str | None, list] = {}
        for proposal in Proposal.objects(customer=customer).order_by("-version"):
            proposals.setdefault(proposal.opportunity_id, []).append({
                "id": str(proposal.id), "version": proposal.version, "mode": proposal.mode,
                "total": proposal.total, "status": proposal.status,
                "status_label": STATUS_LABELS.get(proposal.status, proposal.status), "sent_at": proposal.sent_at.isoformat() if proposal.sent_at else None,
                "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
            })
        attachments = []
        for lead in leads:
            lead["proposals"] = proposals.get(None if lead["current"] else lead["id"], [])
            attachments += [{**a, "lead_number": lead["number"]} for a in lead["attachments"]]
        conversation = ConversationModel.objects(customer=customer).order_by("-updated_at").first()
        return {
            **self._contact_fields(customer),
            "lead_number": customer.lead_number or 1,
            "in_funnel": in_funnel(customer),
            "current_lead_open": in_funnel(customer) and customer.stage not in CLOSED_STAGES,
            "leads": leads,
            "attachments": attachments,
            "conversation_id": str(conversation.id) if conversation else None,
        }

    def lead_timeline(self, customer_id: str, lead_id: str | None, limit: int = 200) -> list[dict]:
        customer = _get(customer_id)
        opportunity_id = None if lead_id in (None, "", "current") else lead_id
        logs = ServiceLog.objects(customer=customer, opportunity_id=opportunity_id).order_by("-created_at").limit(limit)
        return [log.to_dict() for log in logs]

    # --- Escrita ---------------------------------------------------------------------------

    def _clean(self, data: dict) -> dict:
        cleaned = {}
        for field in CONTACT_FIELDS:
            if field not in data:
                continue
            value = data[field]
            value = value.strip() if isinstance(value, str) else value
            cleaned[field] = value or None
        if cleaned.get("contact_type") is None and "contact_type" in cleaned:
            cleaned["contact_type"] = "lead"
        if cleaned.get("owner") is None and "owner" in cleaned:
            cleaned["owner"] = "sdr"
        for field, choices in (("contact_type", domain.CONTACT_TYPES), ("origin", domain.ORIGINS), ("owner", domain.OWNERS)):
            if cleaned.get(field) and cleaned[field] not in choices:
                raise ValueError(f"Valor inválido para {field}: {cleaned[field]}.")
        return cleaned

    def create(self, data: dict, user=None) -> dict:
        phone = normalize_phone(data.get("phone"))
        if not phone:
            raise ValueError("Telefone inválido. Use DDD e número, por exemplo (62) 99999-1111.")
        existing = find_by_phone(phone)
        if existing:
            raise DuplicateContactError(existing)
        fields = self._clean(data)
        now = datetime.utcnow()
        customer = Customer(phone=phone, agent="response_orchestrator", stage_changed_at=now,
                            created_at=now, updated_at=now, **fields)
        partner = bool(data.get("human_operator"))
        if partner:
            customer.human_operator = True
            customer.owner = "erica"
        customer.save()
        ServiceLogRepository.create_log(
            customer=customer, operator_id=_operator(user), action_type="LEAD_CREATED",
            description="Contato cadastrado na página Contatos." + (" Parceiro (fica com a Erica)." if partner else ""),
        )
        return self.detail(str(customer.id))

    def update(self, customer_id: str, data: dict, user=None) -> dict:
        customer = _get(customer_id)
        fields = self._clean(data)
        if "phone" in data:
            phone = normalize_phone(data.get("phone"))
            if not phone:
                raise ValueError("Telefone inválido.")
            existing = find_by_phone(phone)
            if existing and existing.id != customer.id:
                raise DuplicateContactError(existing)
            if phone not in phone_variants(customer.phone):
                fields["phone"] = phone
        changed = [f for f, v in fields.items() if getattr(customer, f) != v]
        for field in changed:
            setattr(customer, field, fields[field])

        if "human_operator" in data and bool(data["human_operator"]) != bool(customer.human_operator):
            if data["human_operator"]:
                self._apply_partner(customer, user, "Marcado como parceiro na página Contatos.", keep_type=True)
            else:
                # Parceiro é contato da Erica (regra 1): só ela tira da lista e devolve para a fila da SDR.
                from crm.services.pipeline_service import PermissionDeniedError
                from users.permissions import has_role
                if not has_role(user):
                    raise PermissionDeniedError("Só a Erica (admin) desmarca um parceiro.")
                customer.human_operator = False
                if customer.owner == "erica":
                    customer.owner = "sdr"
                changed.append("human_operator")
        if changed:
            customer.updated_at = datetime.utcnow()
            customer.save()
            ServiceLogRepository.create_log(
                customer=customer, operator_id=_operator(user), action_type="CONTACT_UPDATED",
                description="Contato atualizado: " + ", ".join(sorted(set(changed))) + ".",
                metadata={"fields": sorted(set(changed))},
            )
        return self.detail(customer_id)

    def _apply_partner(self, customer: Customer, user=None, description: str = "", keep_type: bool = False) -> None:
        """Parceiro ou cliente antigo: fica com a Erica, sai da fila da SDR e a IA não responde.
        Diferente de `mark_human_operator`, não avisa a Erica (uso em lote ou cadastro)."""
        customer.human_operator = True
        customer.owner = "erica"
        if not keep_type and (customer.contact_type or "lead") == "lead":
            customer.contact_type = "parceiro"
        customer.flags = [f for f in (customer.flags or []) if f != "ligacao_pendente"]
        customer.updated_at = datetime.utcnow()
        customer.save()
        SdrTask.objects(customer=customer, status="pending").update(set__status="canceled")

        from chat.models.conversation_model import ConversationModel
        ConversationModel.objects(customer=customer, status__in=["OPEN", "IN_PROGRESS"]).update(
            set__tag="OPERADOR", set__ai_active=False)
        ServiceLogRepository.create_log(
            customer=customer, operator_id=_operator(user), action_type="HUMAN_OPERATOR",
            description=description or "Marcado como parceiro.", metadata={"silent": True},
        )

    # --- Novo lead para um contato existente -------------------------------------------------

    def archive_current_lead(self, customer: Customer, user=None, now: datetime | None = None) -> Opportunity:
        """Copia o lead atual (encerrado) para `opportunities` e limpa o Customer para um lead novo."""
        now = now or datetime.utcnow()
        opportunity = Opportunity(
            customer=customer, number=customer.lead_number or 1, stage=customer.stage,
            started_at=customer.lead_started_at or customer.created_at,
            closed_at=customer.stage_changed_at or now, archived_at=now, archived_by=_operator(user),
            **{field: getattr(customer, field) for field in LEAD_FIELDS},
        ).save()
        opportunity_id = str(opportunity.id)

        from sales.models import Proposal
        Proposal.objects(customer=customer, opportunity_id=None).update(set__opportunity_id=opportunity_id)
        ServiceLog.objects(customer=customer, opportunity_id=None).update(set__opportunity_id=opportunity_id)
        SdrTask.objects(customer=customer, status="pending").update(set__status="canceled")

        for field, value in EMPTY_LEAD.items():
            setattr(customer, field, value.copy() if isinstance(value, (dict, list)) else value)
        customer.owner = "erica" if customer.human_operator else "sdr"
        customer.customer_state_now = domain.NEW_LEAD
        customer.stage_changed_at = now
        customer.lead_number = (customer.lead_number or 1) + 1
        customer.lead_started_at = now
        customer.updated_at = now
        customer.save()
        ServiceLogRepository.create_log(
            customer=customer, operator_id=_operator(user), action_type="NEW_LEAD_OPENED",
            description=f"Novo lead aberto (lead {customer.lead_number} do contato). O lead anterior "
                        f"({domain.STAGE_LABELS[opportunity.stage]}) foi para o histórico.",
            metadata={"previous_opportunity_id": opportunity_id},
        )
        return opportunity

    def start_new_lead(self, customer_id: str, product: str, user=None) -> dict:
        """Abre um lead para o contato. Exige que o lead atual esteja encerrado (ou ainda vazio)."""
        if product not in domain.PRODUCTS:
            raise ValueError(f"Produto inválido: {product}.")
        customer = _get(customer_id)
        has_lead = has_current_lead(customer) and (customer.product or customer.stage != domain.NEW_LEAD)
        # Lead de antes do funil zerado (fora do quadro): vai para o histórico e o contato começa um novo.
        stale_lead = has_lead and not in_funnel(customer)
        if has_lead and not stale_lead and customer.stage not in CLOSED_STAGES:
            raise ValueError("Este contato já tem um lead em andamento. Encerre-o (contrato assinado ou perdido) "
                             "antes de abrir outro.")
        if customer.human_operator:
            raise ValueError("Contato de parceiro fica com a Erica e não entra no funil. Desmarque 'parceiro' antes.")
        if stale_lead and customer.stage not in CLOSED_STAGES:
            self.archive_current_lead(customer, user=user)
            customer.reload()
        if (customer.contact_type or "lead") not in ("lead", "cliente"):
            customer.contact_type = "lead"
            customer.save()

        from crm.container import CrmContainer
        # start_lead arquiva o lead encerrado e abre o novo (mesma regra usada pela IA).
        CrmContainer.get_lead_qualification_service().start_lead(customer_id, product, user=user)
        return self.detail(customer_id)

    # --- Importação de parceiros (CSV) -------------------------------------------------------

    @staticmethod
    def parse_csv(content: str) -> list[tuple[int, str, str | None]]:
        """Linhas (número da linha, telefone como veio, nome). Aceita vírgula, ponto e vírgula ou
        tabulação, com ou sem cabeçalho; sem cabeçalho, a coluna do telefone é a que tem dígitos."""
        content = (content or "").lstrip("﻿")
        sample = content[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(io.StringIO(content), dialect))
        if not rows:
            return []
        header = [_plain(cell) for cell in rows[0]]
        phone_col = next((i for i, h in enumerate(header) if h in PHONE_HEADERS), None)
        name_col = next((i for i, h in enumerate(header) if h in NAME_HEADERS), None)
        start = 1 if phone_col is not None else 0

        parsed = []
        for index, row in enumerate(rows[start:], start=start + 1):
            cells = [c.strip() for c in row]
            if not any(cells):
                continue
            if phone_col is not None:
                phone = cells[phone_col] if phone_col < len(cells) else ""
                name = cells[name_col] if name_col is not None and name_col < len(cells) else None
            else:
                phone_idx = next((i for i, c in enumerate(cells)
                                  if sum(ch.isdigit() for ch in c) >= 8 and not any(ch.isalpha() for ch in c)), None)
                phone = cells[phone_idx] if phone_idx is not None else (cells[0] if cells else "")
                name = next((c for i, c in enumerate(cells) if i != phone_idx and c), None)
            parsed.append((index, phone, name or None))
        return parsed

    def import_partners(self, content: str, user=None, dry_run: bool = False) -> dict:
        """Marca como parceiro (Erica, fora da fila da SDR, IA não responde) os telefones do CSV.
        Contato novo é criado; existente é atualizado. `dry_run` só mostra o que faria."""
        rows = self.parse_csv(content)
        if len(rows) > MAX_IMPORT_ROWS:
            raise ValueError(f"Arquivo com mais de {MAX_IMPORT_ROWS} linhas. Divida em partes.")
        result = {"total": len(rows), "created": 0, "updated": 0, "unchanged": 0, "invalid": [], "repeated": 0,
                  "rows": [], "dry_run": dry_run}
        seen: set[str] = set()
        for line, raw_phone, name in rows:
            phone = normalize_phone(raw_phone)
            if not phone:
                result["invalid"].append({"line": line, "value": raw_phone, "reason": "Telefone inválido"})
                continue
            variants = set(phone_variants(phone))
            if variants & seen:
                result["repeated"] += 1
                continue
            seen |= variants
            existing = find_by_phone(phone)
            if existing and existing.human_operator:
                action = "unchanged"
            elif existing:
                action = "updated"
                if not dry_run:
                    if name and (not existing.name or existing.name.startswith("WhatsApp ")):
                        existing.name = name[:120]
                    self._apply_partner(existing, user, "Marcado como parceiro (importação da lista da Erica).")
            else:
                action = "created"
                if not dry_run:
                    now = datetime.utcnow()
                    customer = Customer(
                        phone=phone, name=(name or None) and name[:120], agent="response_orchestrator",
                        contact_type="parceiro", origin="parceiro", owner="erica", human_operator=True,
                        new_service=False, stage_changed_at=now, created_at=now, updated_at=now,
                    ).save()
                    ServiceLogRepository.create_log(
                        customer=customer, operator_id=_operator(user), action_type="LEAD_CREATED",
                        description="Parceiro importado da lista da Erica.", metadata={"import": True},
                    )
            result[action] += 1
            if len(result["rows"]) < 50:
                result["rows"].append({"line": line, "phone": phone, "name": name,
                                       "existing_name": existing.name if existing else None, "action": action})
        return result
