"""Propostas: cálculo com estoque do período, versões, aprovação da Erica, envio e aceite."""
import base64
import os
from dataclasses import fields as dataclass_fields
from datetime import date, datetime, timedelta

from bson import ObjectId
from django.core import signing

from crm import domain
from crm.container import CrmContainer
from crm.models.custumer_model import Customer
from crm.models.lm_settings_model import LmSettings
from crm.repositories.log_service_repository import ServiceLogRepository
from crm.services.business_hours import business_slot, to_local
from crm.services.notification_service import card_link, format_phone
from crm.services.pipeline_service import PermissionDeniedError
from inventory.services.inventory_service import InventoryService
from sales.formatting import format_brl
from sales.models import Proposal
from sales.services.pricing_service import calc_config, effective_price_table
from sales.services.proposal_pdf import build_pdf_context, file_name as pdf_file_name, render_pdf
from sales.services.quote_calculator import (
    CorporateInput, QuoteResult, SingleProductInput, SocialInput, apply_final_total, calculate_corporativo,
    calculate_porta, calculate_produto_unico, calculate_social, rental_periods, sound_system_for,
)
from users.permissions import has_role
from utils.logger import logger

AVAILABLE_MODES = ("porta", "corporativo", "social", "produto_unico")

EVENT_INPUTS = {"corporativo": CorporateInput, "social": SocialInput}


PDF_SIGNING_SALT = "lm-proposal-pdf"
PDF_LINK_MAX_AGE = 180 * 24 * 3600  # link assinado do PDF vale 180 dias


def signed_pdf_url(proposal_id: str, file_name: str = "proposta.pdf") -> str:
    """Link do PDF que abre sem login (usado na conversa e para compartilhar)."""
    token = signing.dumps(str(proposal_id), salt=PDF_SIGNING_SALT)
    base = os.getenv("BACKEND_PUBLIC_URL", "").rstrip("/")
    return f"{base}/api/v1/sales/proposals/{proposal_id}/pdf/{file_name}?t={token}"


def valid_pdf_token(proposal_id: str, token: str | None) -> bool:
    if not token:
        return False
    try:
        return signing.loads(token, salt=PDF_SIGNING_SALT, max_age=PDF_LINK_MAX_AGE) == str(proposal_id)
    except signing.BadSignature:
        return False


def _parse_day(value, label: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        raise ValueError(f"Informe {label}.")
    text = str(value)[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Data inválida em {label}.")


def _build(input_cls, inputs: dict):
    """Monta o dataclass de entrada ignorando chaves que não são dele (ex.: event_date)."""
    allowed = {f.name for f in dataclass_fields(input_cls)}
    return input_cls(**{k: v for k, v in inputs.items() if k in allowed})


def _operator(user):
    return str(user.id) if user is not None and getattr(user, "id", None) else None


def _customer(customer_id: str) -> Customer:
    try:
        customer = Customer.objects(id=ObjectId(customer_id)).first()
    except Exception:
        customer = None
    if not customer:
        raise ValueError("Lead não encontrado.")
    return customer


def _mirror_value_to_quote(customer: Customer, total: float, sent_at: datetime | None = None):
    """Valor da proposta também na cotação ativa (coleção `quotes`), que o perfil do WhatsApp e a página
    de Leads leem; sem isso, eles mostravam o valor antigo da cotação. Grava direto, sem o espelho
    cotação -> lead (crm.services.quote_sync), que copiaria de volta os outros campos da cotação."""
    try:
        from crm.repositories.quote_repository import QuoteRepository
        quote = QuoteRepository().get_active_by_customer(customer)
        if not quote:
            return
        updates = {"set__quoted_amount": total, "set__updated_at": datetime.utcnow()}
        if sent_at:
            updates["set__proposal_sent_at"] = sent_at
        type(quote).objects(id=quote.id).update_one(**updates)
    except Exception as e:  # o valor no lead já está certo; a cotação é só espelho
        logger.error(f"[Proposal] Falha ao levar o valor da proposta para a cotação: {e}")


def _proposal(proposal_id: str) -> Proposal:
    try:
        proposal = Proposal.objects(id=ObjectId(proposal_id)).first()
    except Exception:
        proposal = None
    if not proposal:
        raise ValueError("Proposta não encontrada.")
    return proposal


class ProposalService:
    def __init__(self, inventory: InventoryService | None = None):
        self.inventory = inventory or InventoryService()

    # --- Cálculo -------------------------------------------------------------------------

    def _period(self, mode: str, inputs: dict, customer: Customer | None) -> tuple[datetime, datetime]:
        if mode == "porta":
            start = _parse_day(inputs.get("pickup_date"), "a data de retirada")
            end = _parse_day(inputs.get("return_date"), "a data de devolução")
        else:
            event_day = inputs.get("event_date") or (customer.event_date if customer and customer.event_date else None)
            start = _parse_day(event_day, "a data do evento")
            end = _parse_day(inputs.get("end_date"), "o fim do evento") if inputs.get("end_date") else start
        return datetime.combine(start, datetime.min.time()), datetime.combine(end, datetime.min.time()) + timedelta(days=1)

    @staticmethod
    def _requested_codes(mode: str, inputs: dict, table: dict) -> set[str]:
        if mode in ("porta", "produto_unico"):
            return {i["code"] for i in inputs.get("items") or []}
        codes = {sound_system_for(int(inputs.get("guests") or 0) or 1, table), "som_sub_duplo", "som_backline",
                 "som_mic_sem_fio", "som_mesa_digital", "som_cerimonia", "palco_forrado", "palco_sem_forracao",
                 "palco_praticavel_2x1", "palco_backdrop", "palco_passa_cabo", "video_led_corporativo",
                 "video_led_social", "video_tecnico_led", "video_estrutura_led", "video_tp", "video_passador_slides"}
        codes |= set((inputs.get("lights") or {}).keys())
        codes |= {i["code"] for i in inputs.get("extra_items") or []}
        kit = (table.get("kits") or {}).get(inputs.get("structure") or "")
        codes |= {p["code"] for p in (kit or {}).get("pieces", [])}
        return codes

    def calculate(self, mode: str, inputs: dict, customer: Customer | None = None,
                  exclude_proposal: str | None = None, user=None) -> tuple[QuoteResult, datetime, datetime]:
        """Calcula a proposta. Entradas comuns a todos os modos: `price_overrides` ({código: preço
        unitário editado}) e `final_total` (valor final editado). Baixar preço ou total trava como
        desconto, exceto para a Erica (admin), que pode dar desconto sem pedir aprovação."""
        if mode not in AVAILABLE_MODES:
            raise ValueError("Modo de proposta inválido.")
        table = effective_price_table()
        overrides = inputs.get("price_overrides") or {}
        if not isinstance(overrides, dict):
            raise ValueError("Preços editados inválidos.")
        table["unit_overrides"] = {code: value for code, value in overrides.items() if value not in (None, "")}
        config = calc_config()
        start, end = self._period(mode, inputs, customer)
        availability = self.inventory.availability(self._requested_codes(mode, inputs, table), start, end, exclude_proposal)
        last_day = (end - timedelta(days=1)).date()
        if mode == "porta":
            result = calculate_porta(inputs.get("items") or [], start.date(), last_day, table, config, availability)
        elif mode == "produto_unico":
            data = _build(SingleProductInput, inputs)
            periods = rental_periods(start.date(), last_day, config.base_period_days)
            result = calculate_produto_unico(data, table, config, availability, periods=periods)
        else:
            data = _build(EVENT_INPUTS[mode], inputs)
            calculate_event = calculate_social if mode == "social" else calculate_corporativo
            result = calculate_event(data, table, config, availability)
        apply_final_total(result, inputs.get("final_total"), config)
        if user is not None and has_role(user):
            result.lock_reasons = [r for r in result.lock_reasons if r["code"] != "desconto"]
        return result, start, end

    # --- Salvar (nova versão) ------------------------------------------------------------

    def save(self, customer_id: str, mode: str, inputs: dict, user=None, replaces: str | None = None) -> dict:
        customer = _customer(customer_id)
        if float(inputs.get("manual_adjustment") or 0) != 0 and not has_role(user):
            raise PermissionDeniedError("Só a Erica (admin) pode aplicar ajuste manual.")
        result, start, end = self.calculate(mode, inputs, customer, exclude_proposal=replaces, user=user)
        data = result.to_dict()

        last = Proposal.objects(customer=customer).order_by("-version").first()
        if replaces:
            previous = _proposal(replaces)
            if previous.customer.id != customer.id or previous.opportunity_id:
                raise ValueError("A proposta substituída não é do lead atual deste cliente.")
            if previous.status == "aceita":
                raise ValueError("Proposta aceita não pode ser editada.")
            previous.status = "substituida"
            previous.updated_at = datetime.utcnow()
            previous.save()
            self.inventory.release(str(previous.id))

        proposal = Proposal(
            customer=customer, version=(last.version + 1) if last else 1, author_id=_operator(user), mode=mode,
            inputs=inputs, lines=data["lines"], costs=data["operational"], items_total=data["items_total"],
            costs_total=data["costs_total"], margin_pct=data["margin_pct"], with_invoice=data["with_invoice"],
            invoice_value=data["invoice_value"], discount=data["discount"],
            manual_adjustment=data["manual_adjustment"], total=data["total"], periods=data["periods"],
            status="aguardando_aprovacao" if result.locked else "rascunho", lock_reasons=data["lock_reasons"],
            warnings=data["warnings"], requires_technical_visit=data["requires_technical_visit"],
            requires_meeting=data["requires_meeting"],
            period_start=start, period_end=end,
        ).save()
        ServiceLogRepository.create_log(
            customer=customer, operator_id=_operator(user), action_type="LEAD_UPDATED",
            description=f"Proposta v{proposal.version} ({mode}) salva: {format_brl(proposal.total)}.",
            metadata={"proposal_id": str(proposal.id), "version": proposal.version, "total": proposal.total},
        )
        # Fazer proposta é atender: o lead passa a aparecer no funil
        from crm.services.funnel_entry import enter_funnel
        enter_funnel(customer)
        if result.locked:
            self._request_approval(proposal, user)
        return proposal.to_dict()

    def _request_approval(self, proposal: Proposal, user=None):
        customer = proposal.customer
        proposal.approval = {"requested_at": datetime.utcnow(), "requested_by": _operator(user)}
        proposal.save()
        flags = ["aguardando_aprovacao_desconto"] + (["aguardando_erica"] if proposal.requires_meeting else [])
        CrmContainer.get_pipeline_service().set_flags(str(customer.id), add=flags, user=user)
        reasons = "; ".join(f"{r['message']}" + (f" ({r['detail']})" if r.get("detail") else "") for r in proposal.lock_reasons)
        ServiceLogRepository.create_log(
            customer=customer, operator_id=_operator(user), action_type="APPROVAL_REQUESTED",
            description=f"Aprovação solicitada para a proposta v{proposal.version}: {reasons}.",
            metadata={"proposal_id": str(proposal.id), "lock_reasons": proposal.lock_reasons},
        )
        text = "\n".join([
            "Aprovação pendente.",
            f"Cliente: {customer.name or 'sem nome'} - {format_phone(customer.phone)}",
            f"Proposta v{proposal.version}: {format_brl(proposal.total)}",
            f"Motivo: {reasons}",
            *(["Evento social fora do padrão da SDR: agendar reunião com a Erica."] if proposal.requires_meeting else []),
            f"Card: {card_link(str(customer.id))}",
        ])
        CrmContainer.get_notification_service().notify_approval(text)

    # --- Aprovação ----------------------------------------------------------------------

    def decide(self, proposal_id: str, approve: bool, user=None, note: str | None = None) -> dict:
        if not has_role(user):
            raise PermissionDeniedError("Só a Erica (admin) aprova propostas.")
        proposal = _proposal(proposal_id)
        if proposal.status != "aguardando_aprovacao":
            raise ValueError("Esta proposta não está aguardando aprovação.")
        proposal.status = "aprovada" if approve else "recusada"
        proposal.approval = {**(proposal.approval or {}), "decided_at": datetime.utcnow(),
                             "decided_by": _operator(user), "decision": proposal.status, "note": note}
        proposal.updated_at = datetime.utcnow()
        proposal.save()
        customer = proposal.customer
        still_waiting = Proposal.objects(customer=customer, status="aguardando_aprovacao").count()
        if not still_waiting:
            CrmContainer.get_pipeline_service().set_flags(str(customer.id), remove=["aguardando_aprovacao_desconto"], user=user)
        ServiceLogRepository.create_log(
            customer=customer, operator_id=_operator(user), action_type="APPROVAL_DECIDED",
            description=f"Proposta v{proposal.version} {'aprovada' if approve else 'recusada'} pela Erica."
            + (f" {note}" if note else ""),
            metadata={"proposal_id": str(proposal.id), "decision": proposal.status},
        )
        return proposal.to_dict()

    # --- Envio e aceite -----------------------------------------------------------------

    @staticmethod
    def _check_current_lead(proposal: Proposal):
        if proposal.opportunity_id:
            raise ValueError("Esta proposta é de um lead anterior do contato (histórico) e não pode ser alterada.")

    @classmethod
    def _check_sendable(cls, proposal: Proposal):
        cls._check_current_lead(proposal)
        if proposal.status == "aguardando_aprovacao":
            raise ValueError("A proposta está travada aguardando a aprovação da Erica.")
        if proposal.status not in ("rascunho", "aprovada", "enviada"):
            raise ValueError(f"Proposta {proposal.status} não pode ser enviada.")

    def send(self, proposal_id: str, user=None, now: datetime | None = None, channel: str | None = None) -> dict:
        """Marca como enviada (o envio ao cliente pode ter sido fora da plataforma)."""
        proposal = _proposal(proposal_id)
        self._check_sendable(proposal)
        now = now or datetime.utcnow()
        cfg = LmSettings.get()
        proposal.status = "enviada"
        proposal.sent_at = now
        proposal.valid_until = now + timedelta(days=cfg.proposal_validity_days)
        proposal.updated_at = now
        proposal.save()

        customer = proposal.customer
        customer.quoted_amount = proposal.total
        customer.proposal_sent_at = now
        customer.updated_at = now
        customer.save()
        _mirror_value_to_quote(customer, proposal.total, sent_at=now)
        if customer.stage in (domain.NEW_LEAD, domain.QUALIFIED, domain.LOST):
            CrmContainer.get_pipeline_service().change_stage(str(customer.id), domain.PROPOSAL_SENT, user=user, system=True,
                                                             note=f"Proposta v{proposal.version} enviada.")
        ServiceLogRepository.create_log(
            customer=customer, operator_id=_operator(user), action_type="PROPOSAL_SENT",
            description=f"Proposta v{proposal.version} enviada: {format_brl(proposal.total)}. "
                        f"Válida até {proposal.valid_until.strftime('%d/%m/%Y')}."
                        + (" PDF enviado pelo WhatsApp." if channel == "whatsapp" else ""),
            metadata={"proposal_id": str(proposal.id), "total": proposal.total, "channel": channel or "manual"},
        )
        tasks = CrmContainer.get_sdr_task_service()
        tasks.complete_pending(str(customer.id), ["ligar_15min"], user=user)
        tasks.cancel_cadence(str(customer.id))  # nova versão reinicia o D+1, D+3, D+5
        warn_day = to_local(now).date() + timedelta(days=max(cfg.proposal_warning_day, 1))
        warn_at = business_slot(cfg.business_hours, warn_day, cfg.first_call_hour) or now + timedelta(days=cfg.proposal_warning_day)
        tasks.create_task(str(customer.id), "proposta_vencendo", due_at=warn_at,
                          metadata={"proposal_id": str(proposal.id)}, unique_pending=False)
        return proposal.to_dict()

    # --- PDF -------------------------------------------------------------------------------

    def render_pdf(self, proposal: Proposal, valid_until: datetime | None = None,
                   issued_at: datetime | None = None) -> tuple[bytes, str]:
        cfg = LmSettings.get()
        issued_at = issued_at or proposal.sent_at or datetime.utcnow()
        valid_until = valid_until or proposal.valid_until or issued_at + timedelta(days=cfg.proposal_validity_days)
        context = build_pdf_context(proposal.to_dict(), proposal.customer.to_dict(), cfg.to_dict(),
                                    valid_until=valid_until, issued_at=issued_at)
        return render_pdf(context), pdf_file_name(context)

    def pdf(self, proposal_id: str) -> tuple[bytes, str]:
        return self.render_pdf(_proposal(proposal_id))

    def send_whatsapp(self, proposal_id: str, user=None, now: datetime | None = None) -> dict:
        """Gera o PDF, envia no WhatsApp do cliente e marca a proposta como enviada (um clique)."""
        proposal = _proposal(proposal_id)
        self._check_sendable(proposal)
        customer = proposal.customer
        now = now or datetime.utcnow()
        valid_until = now + timedelta(days=LmSettings.get().proposal_validity_days)
        content, name = self.render_pdf(proposal, valid_until=valid_until, issued_at=now)
        caption = (f"Proposta comercial LM Eventos: {format_brl(proposal.total)}. "
                   f"Válida até {valid_until.strftime('%d/%m/%Y')}.")
        try:
            from gateway.adapters.zapi_adapter import ZAPIClient
            sent = ZAPIClient().send_document(
                phone=customer.phone, document="data:application/pdf;base64," + base64.b64encode(content).decode(),
                file_name=name, caption=caption,
            )
        except Exception as e:
            logger.error(f"[Proposal] Falha ao enviar o PDF da proposta {proposal_id}: {e}")
            sent = None
        if not sent:
            raise ValueError("Não foi possível enviar o PDF pelo WhatsApp. Tente novamente ou envie manualmente.")

        data = self.send(proposal_id, user=user, now=now, channel="whatsapp")
        proposal.reload()
        proposal.pdf_url = signed_pdf_url(str(proposal.id), name)
        proposal.save()
        self._record_in_conversation(customer, caption, name, proposal.pdf_url, user)
        return {**data, "pdf_url": proposal.pdf_url}

    @staticmethod
    def _record_in_conversation(customer: Customer, caption: str, file_name: str, url: str, user=None):
        """O PDF aparece na conversa da aba WhatsApp como arquivo enviado pelo operador."""
        try:
            from chat.container import ChatContainer
            from chat.models.conversation_model import ConversationModel
            conversation = ConversationModel.objects(customer=customer).order_by("-updated_at").first()
            if not conversation:
                return
            ChatContainer.get_message_service()._save_and_notify(
                conversation_id=str(conversation.id), content=caption, direction="OUTGOING", sender_role="OPERATOR",
                raw_metadata={"document": {"documentUrl": url, "fileName": file_name}, "operator_id": _operator(user)},
                message_type="file", media_url=url, status="SENT_TO_GATEWAY",
            )
            conversation.last_message_content = f"[Arquivo] {file_name}"
            conversation.updated_at = datetime.utcnow()
            conversation.save()
        except Exception as e:
            # O PDF já foi enviado ao cliente; falha ao registrar na conversa não desfaz o envio.
            logger.error(f"[Proposal] Falha ao registrar o PDF na conversa: {e}")

    def stock_shortages(self, proposal: Proposal) -> list[str]:
        """Itens próprios e contados da proposta que faltam no período hoje (outras propostas podem
        ter sido aceitas depois que esta foi calculada)."""
        lines = [l for l in proposal.lines or [] if l.get("owned", True)]
        available = self.inventory.availability({l["code"] for l in lines}, proposal.period_start,
                                                proposal.period_end, exclude_proposal=str(proposal.id))
        requested: dict[str, float] = {}
        names: dict[str, str] = {}
        for line in lines:
            requested[line["code"]] = requested.get(line["code"], 0) + float(line["qty"])
            names[line["code"]] = line.get("name") or line["code"]
        return [f"{names[code]}: pedido {qty:g}, disponível {available[code]:g}"
                for code, qty in requested.items() if available.get(code) is not None and qty > available[code]]

    def accept(self, proposal_id: str, user=None, note: str | None = None) -> dict:
        """Cliente aceitou: confere o estoque de novo, reserva o período e move o card para
        'Proposta aceita'. Faltando peça, só a Erica (admin) aceita mesmo assim."""
        proposal = _proposal(proposal_id)
        self._check_current_lead(proposal)
        if proposal.status != "enviada":
            raise ValueError("Só uma proposta enviada pode ser marcada como aceita.")
        shortages = self.stock_shortages(proposal)
        if shortages and not has_role(user):
            raise ValueError("Estoque insuficiente no período para aceitar esta proposta: " + "; ".join(shortages)
                             + ". Fale com a Erica antes de confirmar com o cliente.")
        customer = proposal.customer
        if customer.stage not in (domain.PROPOSAL_ACCEPTED, domain.CONTRACT_SIGNED):
            CrmContainer.get_pipeline_service().change_stage(str(customer.id), domain.PROPOSAL_ACCEPTED, user=user,
                                                             system=True, note=note)
        now = datetime.utcnow()
        proposal.status = "aceita"
        proposal.accepted_at = now
        proposal.updated_at = now
        proposal.save()
        # O valor do card e dos painéis passa a ser o da versão aceita (pode não ser a última enviada)
        customer.reload()
        customer.quoted_amount = proposal.total
        customer.updated_at = now
        customer.save()
        _mirror_value_to_quote(customer, proposal.total)
        reserved = self.inventory.reserve(str(proposal.id), customer, proposal.lines, proposal.period_start,
                                          proposal.period_end)
        CrmContainer.get_sdr_task_service().cancel_pending_for_customer(str(customer.id))
        if proposal.mode == "porta":
            customer.reload()
            customer.owner = "lucia"
            customer.save()
            items = ", ".join(f"{int(l['qty']) if float(l['qty']).is_integer() else l['qty']} {l['name']}" for l in proposal.lines)
            CrmContainer.get_notification_service().notify_lucia("\n".join([
                "Locação de porta fechada.",
                f"Cliente: {customer.name or 'sem nome'} - {format_phone(customer.phone)}",
                f"Retirada: {proposal.period_start.strftime('%d/%m/%Y')}",
                f"Devolução: {(proposal.period_end - timedelta(days=1)).strftime('%d/%m/%Y')}",
                f"Itens: {items}",
                f"Total: {format_brl(proposal.total)}",
                f"Card: {card_link(str(customer.id))}",
            ]))
        ServiceLogRepository.create_log(
            customer=customer, operator_id=_operator(user), action_type="LEAD_UPDATED",
            description=f"Proposta v{proposal.version} aceita." + (" Estoque reservado." if reserved else "")
            + (f" Aceita pela Erica com falta de estoque: {'; '.join(shortages)}." if shortages else ""),
            metadata={"proposal_id": str(proposal.id), "shortages": shortages},
        )
        return proposal.to_dict()

    def undo_acceptance(self, customer: Customer, back_to_sent: bool, user=None) -> int:
        """O card saiu de 'Proposta aceita' (voltou para 'Proposta enviada' ou foi perdido): a
        proposta aceita volta para enviada (ou recusada) e o estoque reservado é liberado.
        Peças já retiradas continuam como retiradas até o retorno."""
        count = 0
        for proposal in Proposal.objects(customer=customer, opportunity_id=None, status="aceita"):
            proposal.status = "enviada" if back_to_sent else "recusada"
            proposal.accepted_at = None
            proposal.updated_at = datetime.utcnow()
            proposal.save()
            released = self.inventory.release(str(proposal.id))
            ServiceLogRepository.create_log(
                customer=customer, operator_id=_operator(user), action_type="LEAD_UPDATED",
                description=f"Aceite da proposta v{proposal.version} desfeito"
                + (" (voltou para enviada)." if back_to_sent else " (lead perdido).")
                + (" Estoque liberado." if released else ""),
                metadata={"proposal_id": str(proposal.id), "released": released},
            )
            count += 1
        if count and customer.owner == "lucia" and not customer.human_operator:
            Customer.objects(id=customer.id).update(set__owner="sdr")
        if count and back_to_sent:
            # De volta a "enviada": o valor do card volta a ser o da última versão enviada
            latest = Proposal.objects(customer=customer, opportunity_id=None, status="enviada").order_by("-version").first()
            if latest:
                Customer.objects(id=customer.id).update(set__quoted_amount=latest.total, set__updated_at=datetime.utcnow())
                _mirror_value_to_quote(customer, latest.total)
        return count

    def reject(self, proposal_id: str, user=None, note: str | None = None) -> dict:
        proposal = _proposal(proposal_id)
        if proposal.status in ("aceita", "substituida"):
            raise ValueError(f"Proposta {proposal.status} não pode ser recusada.")
        proposal.status = "recusada"
        proposal.updated_at = datetime.utcnow()
        proposal.save()
        self.inventory.release(str(proposal.id))
        ServiceLogRepository.create_log(
            customer=proposal.customer, operator_id=_operator(user), action_type="LEAD_UPDATED",
            description=f"Proposta v{proposal.version} recusada pelo cliente." + (f" {note}" if note else ""),
            metadata={"proposal_id": str(proposal.id)},
        )
        return proposal.to_dict()

    def cancel_acceptance(self, proposal_id: str, user=None) -> dict:
        """Cancela uma proposta aceita (cliente desistiu): libera o estoque."""
        proposal = _proposal(proposal_id)
        if proposal.status != "aceita":
            raise ValueError("Só proposta aceita pode ser cancelada.")
        proposal.status = "recusada"
        proposal.save()
        self.inventory.release(str(proposal.id))
        return proposal.to_dict()

    def expire(self, now: datetime | None = None) -> int:
        now = now or datetime.utcnow()
        count = 0
        for proposal in Proposal.objects(status="enviada", valid_until__lt=now):
            proposal.status = "vencida"
            proposal.updated_at = now
            proposal.save()
            ServiceLogRepository.create_log(
                customer=proposal.customer, operator_id=None, action_type="LEAD_UPDATED",
                description=f"Proposta v{proposal.version} venceu sem resposta.",
                metadata={"proposal_id": str(proposal.id)},
            )
            count += 1
        return count

    def list_for_customer(self, customer_id: str) -> list[dict]:
        return [p.to_dict() for p in Proposal.objects(customer=customer_id, opportunity_id=None).order_by("-version")]

    def pending_approvals(self) -> list[dict]:
        return [p.to_dict() for p in Proposal.objects(status="aguardando_aprovacao").order_by("created_at")]
