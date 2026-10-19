"""Qualificação do lead: serviços prontos para a IA chamar a partir das functions (e para a SDR
pelo card). Não depende de nada em ai_agents/. Ver crm/README.md."""
import unicodedata
from datetime import datetime

from bson import ObjectId

from crm import domain
from crm.models.custumer_model import Customer
from crm.models.lm_settings_model import LmSettings
from crm.repositories.log_service_repository import ServiceLogRepository
from crm.services.business_hours import first_call_due, to_local
from crm.services.notification_service import card_link, format_phone
from utils.logger import logger
from utils.safe_url import safe_media_url

# Campos comuns a todos os produtos
COMMON_FIELDS = (
    "nome", "email", "empresa", "cargo", "origem", "cidade", "local", "data_evento",
    "horario_evento", "publico", "tipo_evento", "titulo_evento", "orcamento_cliente",
    "forma_contato_preferida", "observacoes",
)

# Campos específicos por produto (o que a IA pergunta em cada fluxo)
PRODUCT_FIELDS = {
    "estrutura_porta": (
        "data_retirada", "data_devolucao", "lista_pecas", "linha_estrutura", "uso_estrutura",
        "forma_retirada",
    ),
    "estrutura_montagem": (
        "data_montagem", "data_desmontagem", "estrutura_desejada", "medidas", "altura_local",
        "piso_local", "acesso_caminhao", "projeto",
    ),
    "corporativo": (
        "estilo", "palco_m2", "palco_forrado", "led_m2", "backdrop", "iluminacao", "microfones",
        "tp_retorno", "praticaveis", "banda", "pista", "horario_montagem", "horario_desmontagem",
        "projeto", "orcamento_concorrente", "nota_fiscal",
    ),
    "social": (
        "tipo_celebracao", "led", "dj", "pista", "cerimonia", "piso_microlampadas", "fumaca",
        "projeto", "orcamento_concorrente", "pacote_basico",
    ),
    "produto_unico": (
        "item", "quantidade", "data_uso", "forma_entrega", "endereco_entrega", "precisa_montagem",
    ),
}

# Campos espelhados nos campos que o CRM e o dashboard já usam
MIRRORS = {
    "nome": "name",
    "email": "email",
    "empresa": "company",
    "cargo": "role",
    "local": "venue",
    "data_evento": "event_date",
    "publico": "guest_count",
    "tipo_evento": "celebration_type",
    "tipo_celebracao": "celebration_type",
    "titulo_evento": "event_title",
}

UNKNOWN_ANSWERS = {"nao sei", "não sei", "nao sabe", "não sabe", "nao_sei", "a definir", "indefinido"}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return text.strip().lower()


def fields_for(product: str | None) -> tuple[str, ...]:
    return COMMON_FIELDS + PRODUCT_FIELDS.get(product or "", ())


def _get(customer_id: str) -> Customer:
    try:
        customer = Customer.objects(id=ObjectId(customer_id)).first()
    except Exception:
        customer = None
    if not customer:
        raise ValueError("Lead não encontrado.")
    return customer


def _parse_date(value):
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _parse_int(value):
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else None


class LeadQualificationService:
    """Métodos chamáveis pela IA (functions) e pelos endpoints do card.

    Todos recebem o id do Customer (string) e devolvem o lead atualizado (dict de Customer.to_dict()).
    `user` é opcional: quando vem da IA fica None e a linha do tempo registra como sistema.
    """

    def __init__(self, notification_service=None, task_service=None):
        self._notifications = notification_service
        self._tasks = task_service

    @property
    def notifications(self):
        if self._notifications is None:
            from crm.container import CrmContainer
            self._notifications = CrmContainer.get_notification_service()
        return self._notifications

    @property
    def tasks(self):
        if self._tasks is None:
            from crm.container import CrmContainer
            self._tasks = CrmContainer.get_sdr_task_service()
        return self._tasks

    @staticmethod
    def _operator(user):
        return str(user.id) if user is not None and getattr(user, "id", None) else None

    # ------------------------------------------------------------------------------------

    def start_lead(self, customer_id: str, product: str, user=None) -> dict:
        """Define o produto e coloca o lead em NEW_LEAD.

        Se o lead atual do contato já foi encerrado (contrato assinado ou perdido), ele vai para o
        histórico do contato (`opportunities`) e um lead novo começa do zero.
        """
        if product not in domain.PRODUCTS:
            raise ValueError(f"Produto inválido: {product}. Use um de: {', '.join(domain.PRODUCTS)}.")
        customer = _get(customer_id)
        if customer.stage in (domain.CONTRACT_SIGNED, domain.LOST):
            from crm.services.contact_service import ContactService
            ContactService().archive_current_lead(customer, user=user)
            customer.reload()
        customer.product = product
        customer.contact_type = customer.contact_type or "lead"
        customer.updated_at = datetime.utcnow()
        customer.save()
        if customer.stage != domain.NEW_LEAD:
            from crm.container import CrmContainer
            CrmContainer.get_pipeline_service().change_stage(customer_id, domain.NEW_LEAD, user=user, system=True,
                                                             note="Novo atendimento iniciado.")
            customer.reload()
        ServiceLogRepository.create_log(
            customer=customer, operator_id=self._operator(user), action_type="LEAD_UPDATED",
            description=f"Atendimento iniciado: {domain.PRODUCTS[product]}.", metadata={"product": product},
        )
        return customer.to_dict()

    def save_field(self, customer_id: str, field: str, value, user=None) -> dict:
        """Grava um dado em `qualification` e espelha nos campos do CRM (ver MIRRORS).

        Resposta "não sei" (ou None/vazio) entra em `pending_fields`; um valor real tira o campo de lá.
        Campos aceitos: COMMON_FIELDS + PRODUCT_FIELDS[produto do lead].
        """
        customer = _get(customer_id)
        allowed = fields_for(customer.product)
        if field not in allowed:
            raise ValueError(f"Campo '{field}' não é válido para o produto {customer.product or '(não definido)'}.")

        unknown = value is None or (isinstance(value, str) and (not value.strip() or _normalize(value) in UNKNOWN_ANSWERS))
        qualification = dict(customer.qualification or {})
        pending = [f for f in (customer.pending_fields or []) if f != field]
        if unknown:
            qualification[field] = None
            pending.append(field)
        else:
            qualification[field] = value.isoformat() if isinstance(value, datetime) else value
            target = MIRRORS.get(field)
            if target == "event_date":
                parsed = _parse_date(value)
                if parsed:
                    customer.event_date = parsed
            elif target == "guest_count":
                parsed = _parse_int(value)
                if parsed is not None:
                    customer.guest_count = parsed
            elif target:
                setattr(customer, target, str(value)[:160])
            if field == "origem" and _normalize(value) in domain.ORIGINS:
                customer.origin = _normalize(value)

        customer.qualification = qualification
        customer.pending_fields = pending
        customer.updated_at = datetime.utcnow()
        customer.save()
        ServiceLogRepository.create_log(
            customer=customer, operator_id=self._operator(user), action_type="FIELD_SAVED",
            description=f"{field}: {'não sabe (pendente)' if unknown else value}",
            metadata={"field": field, "pending": unknown},
        )
        return customer.to_dict()

    def add_attachment(self, customer_id: str, url: str, kind: str = "outro", name: str | None = None, user=None) -> dict:
        """Anexa arquivo recebido (rider, projeto, orçamento concorrente, lista de peças, outro)."""
        if not url:
            raise ValueError("Informe a URL do anexo.")
        if not safe_media_url(url):
            raise ValueError("URL do anexo inválida: use um endereço http(s).")
        if kind not in domain.ATTACHMENT_KINDS:
            raise ValueError(f"Tipo de anexo inválido: {kind}.")
        customer = _get(customer_id)
        url = url.strip()
        name = str(name or url.split("?", 1)[0].rsplit("/", 1)[-1])[:160]
        attachment = {"url": url, "kind": kind, "name": name, "received_at": datetime.utcnow()}
        customer.attachments = [*(customer.attachments or []), attachment]
        customer.updated_at = datetime.utcnow()
        customer.save()
        ServiceLogRepository.create_log(
            customer=customer, operator_id=self._operator(user), action_type="ATTACHMENT_ADDED",
            description=f"Anexo recebido: {domain.ATTACHMENT_KINDS[kind]} ({attachment['name']}).",
            metadata={"url": url, "kind": kind},
        )
        return customer.to_dict()

    def qualify_lead(self, customer_id: str, pending_fields: list[str] | None = None, needs_erica: bool = False,
                     user=None, now: datetime | None = None) -> dict:
        """Move para QUALIFIED, cria a tarefa `ligar_15min` e avisa a SDR.

        Fora do horário comercial, a ligação fica para as 9h do próximo dia útil.
        Contato de operador humano não gera tarefa (fica com a Erica).
        Lead que já passou da qualificação (proposta enviada ou aceita, contrato assinado) não volta
        de etapa: só as pendências e o "precisa da Erica" são atualizados, sem nova tarefa de ligação.
        """
        customer = _get(customer_id)
        now = now or datetime.utcnow()
        from crm.container import CrmContainer
        if customer.stage in (domain.PROPOSAL_SENT, domain.PROPOSAL_ACCEPTED, domain.CONTRACT_SIGNED):
            pending = list(customer.pending_fields or [])
            pending += [f for f in (pending_fields or []) if f not in pending]
            customer.pending_fields = pending
            customer.needs_erica = bool(customer.needs_erica or needs_erica)
            if needs_erica and "aguardando_erica" not in (customer.flags or []):
                customer.flags = [*(customer.flags or []), "aguardando_erica"]
            customer.updated_at = now
            customer.save()
            ServiceLogRepository.create_log(
                customer=customer, operator_id=self._operator(user), action_type="LEAD_UPDATED",
                description=f"Qualificação atualizada (lead segue em {domain.STAGE_LABELS[customer.stage]})."
                + (f" Pendências: {', '.join(pending)}." if pending else ""),
                metadata={"pending_fields": pending, "needs_erica": bool(needs_erica), "kept_stage": customer.stage},
            )
            return customer.to_dict()
        if customer.stage != domain.QUALIFIED:
            CrmContainer.get_pipeline_service().change_stage(customer_id, domain.QUALIFIED, user=user, system=True)
            customer.reload()

        pending = list(customer.pending_fields or [])
        pending += [f for f in (pending_fields or []) if f not in pending]
        customer.pending_fields = pending
        customer.qualified_at = now
        customer.needs_erica = bool(needs_erica)
        flags = list(customer.flags or [])
        for flag in ["ligacao_pendente"] + (["aguardando_erica"] if needs_erica else []):
            if flag not in flags:
                flags.append(flag)
        customer.flags = flags
        cfg = LmSettings.get()
        due = first_call_due(cfg.business_hours, now, cfg.call_sla_minutes, cfg.first_call_hour)
        customer.next_step = "Ligar para o lead"
        customer.next_action_at = due
        customer.updated_at = now
        customer.save()

        ServiceLogRepository.create_log(
            customer=customer, operator_id=self._operator(user), action_type="LEAD_QUALIFIED",
            description="Lead qualificado." + (f" Pendências: {', '.join(pending)}." if pending else "")
            + (" Precisa da Erica." if needs_erica else ""),
            metadata={"pending_fields": pending, "needs_erica": bool(needs_erica)},
        )
        task = self.tasks.create_task(customer_id, "ligar_15min", due_at=due)
        if task:
            local_due = to_local(due)
            product = domain.PRODUCTS.get(customer.product, "não informado")
            lines = [
                "Novo lead qualificado.",
                f"Cliente: {customer.name or 'sem nome'} - {format_phone(customer.phone)}",
                f"Produto: {product}",
            ]
            if pending:
                lines.append(f"Pendências: {', '.join(pending)}")
            if needs_erica:
                lines.append("Precisa da avaliação da Erica.")
            lines.append(f"Ligar até {local_due.strftime('%d/%m às %H:%M')}.")
            lines.append(f"Card: {card_link(customer_id)}")
            self.notifications.notify_sdr("\n".join(lines))
        return customer.to_dict()

    def mark_human_operator(self, customer_id: str, reason: str, user=None) -> dict:
        """Parceiro ou cliente antigo: fica com a Erica, sai da fila da SDR, IA pausada na conversa."""
        customer = _get(customer_id)
        customer.human_operator = True
        customer.owner = "erica"
        customer.flags = [f for f in (customer.flags or []) if f != "ligacao_pendente"]
        customer.updated_at = datetime.utcnow()
        customer.save()
        self.tasks.cancel_pending_for_customer(customer_id)

        from chat.models.conversation_model import ConversationModel
        conversation = ConversationModel.objects(customer=customer, status__in=["OPEN", "IN_PROGRESS"]).first()
        if conversation:
            conversation.tag = "OPERADOR"
            conversation.ai_active = False
            conversation.needs_attention = True
            conversation.updated_at = datetime.utcnow()
            conversation.save()

        ServiceLogRepository.create_log(
            customer=customer, operator_id=self._operator(user), action_type="HUMAN_OPERATOR",
            description=f"Encaminhado para a Erica. Motivo: {reason or 'não informado'}.",
            metadata={"reason": reason},
        )
        text = "\n".join([
            "Contato encaminhado para o seu atendimento.",
            f"Contato: {customer.name or 'sem nome'} - {format_phone(customer.phone)}",
            f"Motivo: {reason or 'não informado'}",
            "A assistente virtual foi pausada nesta conversa.",
        ])
        if not self.notifications.notify_erica(text):
            logger.warning(f"[LeadQualification] Aviso para a Erica não enviado ({customer.phone}).")
        return customer.to_dict()
