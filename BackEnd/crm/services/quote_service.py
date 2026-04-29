import os
from datetime import datetime
from typing import Any, Optional
from bson import ObjectId
from utils.logger import logger
from crm.models.custumer_model import Customer
from crm.models.quote_model import Quote
from crm.repositories.customer_repository import CustomerRepository
from crm.repositories.quote_repository import QuoteRepository
from database.client.mongodb_client import MongoDBClient
from chat.models.conversation_model import ConversationModel
from gateway.adapters.zapi_adapter import ZAPIClient


class QuoteService:
    MANUAL_STAGES = {"WON", "LOST"}
    AUTO_STAGES = {"ANALYSIS", "BUDGET", "NEGOTIATING"}
    INTERACTION_FIELDS = {"notes", "last_interaction_at", "next_step"}
    QUOTE_FIELDS = {
        "celebration_type",
        "event_title",
        "event_date",
        "guest_count",
        "quoted_amount",
        "contract_value",
        "venue",
        "notes",
        "proposal_sent_at",
        "last_interaction_at",
        "next_step",
        "status",
        "customer_state_now",
        "actual_status",
    }

    def __init__(self):
        self.quote_repo = QuoteRepository()
        self.customer_repo = CustomerRepository(MongoDBClient())

    def _parse_datetime(self, value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            cleaned = value.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(cleaned)
            except ValueError:
                for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
                    try:
                        return datetime.strptime(value, fmt)
                    except ValueError:
                        continue
        raise ValueError("Data inválida informada.")

    def normalize_quote_data(self, data: dict) -> dict:
        data = dict(data or {})
        if "customer_state_now" in data and "status" not in data:
            data["status"] = data.pop("customer_state_now")
        if "actual_status" in data and "status" not in data:
            data["status"] = data.pop("actual_status")

        numeric_fields = {"guest_count": int, "quoted_amount": float, "contract_value": float}
        datetime_fields = {"event_date", "proposal_sent_at", "last_interaction_at", "closed_at"}

        for field, caster in numeric_fields.items():
            if field in data and data[field] not in (None, ""):
                data[field] = caster(data[field])

        for field in datetime_fields:
            if field in data:
                data[field] = self._parse_datetime(data[field]) if data[field] else None

        return data

    def _infer_stage(self, existing_quote: Optional[dict], payload: dict) -> str:
        requested_stage = payload.get("status")
        current_stage = existing_quote.get("status") if existing_quote else None

        if requested_stage in self.MANUAL_STAGES:
            return requested_stage

        if current_stage in self.MANUAL_STAGES and requested_stage not in self.MANUAL_STAGES:
            return current_stage

        if requested_stage in self.AUTO_STAGES:
            return requested_stage

        quoted_amount = payload.get("quoted_amount")
        if quoted_amount is None and existing_quote:
            quoted_amount = existing_quote.get("quoted_amount")

        contract_value = payload.get("contract_value")
        if contract_value is None and existing_quote:
            contract_value = existing_quote.get("contract_value")

        proposal_sent_at = payload.get("proposal_sent_at")
        if proposal_sent_at is None and existing_quote:
            proposal_sent_at = existing_quote.get("proposal_sent_at")

        has_budget = any(value not in (None, "", 0, 0.0) for value in [quoted_amount, contract_value]) or bool(proposal_sent_at)
        has_interaction = any(payload.get(field) not in (None, "") for field in self.INTERACTION_FIELDS)

        if has_budget and has_interaction:
            return "NEGOTIATING"
        if has_budget:
            return "BUDGET"
        return "ANALYSIS"

    def _customer_document(self, customer_id: str):
        return Customer.objects(id=ObjectId(customer_id)).first()

    def _find_or_create_customer(self, data: dict):
        phone = data.get("phone")
        name = data.get("name")
        if not phone:
            raise ValueError("O número de telefone é obrigatório.")

        customer = Customer.objects(phone=phone).first()
        if customer:
            if name and customer.name != name:
                customer.name = name
                customer.updated_at = datetime.utcnow()
                customer.save()
            return customer

        customer = Customer(name=name, phone=phone, agent="response_orchestrator")
        customer.save()
        return customer

    def quote_payload_from_customer(self, customer: dict) -> dict:
        return {
            "status": customer.get("customer_state_now", "ANALYSIS"),
            "celebration_type": customer.get("celebration_type"),
            "event_title": customer.get("event_title"),
            "event_date": self._parse_datetime(customer.get("event_date")) if customer.get("event_date") else None,
            "guest_count": customer.get("guest_count") or 0,
            "quoted_amount": customer.get("quoted_amount") or 0,
            "contract_value": customer.get("contract_value") or 0,
            "venue": customer.get("venue"),
            "notes": customer.get("notes"),
            "proposal_sent_at": self._parse_datetime(customer.get("proposal_sent_at")) if customer.get("proposal_sent_at") else None,
            "last_interaction_at": self._parse_datetime(customer.get("last_interaction_at")) if customer.get("last_interaction_at") else None,
            "next_step": customer.get("next_step"),
        }

    def _has_budget_payload(self, data: dict) -> bool:
        quoted_amount = data.get("quoted_amount")
        contract_value = data.get("contract_value")
        return any(value not in (None, "", 0, 0.0) for value in [quoted_amount, contract_value])

    def _build_financial_summary(self, quote: dict) -> str:
        def value_or_dash(value):
            return value if value not in (None, "") else "-"

        amount = quote.get("contract_value") or quote.get("quoted_amount") or 0
        return "\n".join(
            [
                "*Orçamento definido*",
                f"Cliente: {value_or_dash(quote.get('name'))}",
                f"Telefone: {value_or_dash(quote.get('phone'))}",
                f"Valor: R$ {float(amount or 0):,.2f}",
                f"Evento/Produto: {value_or_dash(quote.get('event_title') or quote.get('celebration_type'))}",
                f"Data: {value_or_dash(quote.get('event_date'))}",
                f"Local: {value_or_dash(quote.get('venue'))}",
                f"Resumo: {value_or_dash(quote.get('notes'))}",
                f"Próximo passo: {value_or_dash(quote.get('next_step'))}",
            ]
        )

    def _mark_budget_and_notify_finance(self, quote: dict) -> None:
        try:
            conversation = ConversationModel.objects(quote=quote.get("id"), status__in=["OPEN", "IN_PROGRESS"]).first()
            if conversation:
                conversation.tag = "orcamento"
                conversation.ai_active = False
                conversation.needs_attention = True
                conversation.save()

            self.customer_repo.update(
                id=quote["customer_id"],
                attributes={"customer_custom_tag": "orcamento", "updated_at": datetime.utcnow()},
            )

            finance_phone = (
                os.getenv("FINANCE_PHONE")
                or os.getenv("FINANCEIRO_PHONE")
                or os.getenv("ADM_PHONE")
                or os.getenv("REGISTER_PHONE")
                or ""
            ).strip()

            if finance_phone:
                ZAPIClient().send_message(phone=finance_phone, message=self._build_financial_summary(quote))
            else:
                logger.warning("[QuoteService] FINANCE_PHONE não configurado. Resumo financeiro não enviado.")
        except Exception as e:
            logger.error(f"[QuoteService] Falha ao notificar financeiro: {str(e)}")

    def ensure_quote_for_legacy_customer(self, customer_id: str) -> dict | None:
        customer_doc = self._customer_document(customer_id)
        if not customer_doc:
            return None

        existing = Quote.objects(customer=customer_doc).first()
        if existing:
            return existing.to_dict()

        customer = customer_doc.to_dict()
        has_commercial_data = any(
            customer.get(field) not in (None, "", 0, 0.0)
            for field in ["celebration_type", "event_title", "event_date", "guest_count", "quoted_amount", "contract_value", "venue", "notes"]
        )
        if not has_commercial_data:
            return None

        return self.quote_repo.create(customer_doc, self.quote_payload_from_customer(customer))

    def get_or_create_active_quote_for_customer(self, customer_id: str, seed: dict | None = None) -> dict:
        customer_doc = self._customer_document(customer_id)
        if not customer_doc:
            raise ValueError("Cliente não encontrado.")

        active_quote = self.quote_repo.get_active_by_customer(customer_doc)
        if active_quote:
            return active_quote.to_dict()

        attributes = self.normalize_quote_data(seed or {})
        attributes["status"] = self._infer_stage(None, attributes)
        return self.quote_repo.create(customer_doc, attributes)

    def create_quote(self, data: dict, user: Any = None) -> dict:
        data = self.normalize_quote_data(data)
        customer_doc = self._find_or_create_customer(data)
        quote_data = {key: value for key, value in data.items() if key in self.QUOTE_FIELDS or key == "status"}
        quote_data["status"] = self._infer_stage(None, quote_data)
        return self.quote_repo.create(customer_doc, quote_data)

    def list_quotes(self, status_filter: str | None = None, search_term: str | None = None) -> list[dict]:
        for customer in self.customer_repo.get_all_customers():
            self.ensure_quote_for_legacy_customer(customer["id"])
        return self.quote_repo.list(status_filter=status_filter, search_term=search_term)

    def update_quote(self, quote_id: str, data: dict, user: Any = None) -> dict:
        data = self.normalize_quote_data(data)
        existing_quote = self.quote_repo.get_by_id(quote_id)
        if not existing_quote:
            raise ValueError("Cotação não encontrada.")

        data["status"] = self._infer_stage(existing_quote, data)
        updated = self.quote_repo.update(quote_id, data)
        if not updated:
            raise ValueError("Cotação não encontrada.")

        customer_updates = {
            "customer_state_now": updated["status"],
            "updated_at": datetime.utcnow(),
        }
        if data.get("name") not in (None, ""):
            customer_updates["name"] = data.get("name")
        if data.get("phone") not in (None, ""):
            customer_updates["phone"] = data.get("phone")
        self.customer_repo.update(id=updated["customer_id"], attributes=customer_updates)
        if self._has_budget_payload(data):
            self._mark_budget_and_notify_finance(updated)
        return updated

    def close_quote(self, quote_id: str, status_value: str, data: dict | None = None, user: Any = None) -> dict:
        if status_value not in self.MANUAL_STAGES:
            raise ValueError("Status de fechamento deve ser WON ou LOST.")

        payload = self.normalize_quote_data(data or {})
        payload["status"] = status_value
        payload["closed_at"] = datetime.utcnow()
        updated = self.quote_repo.update(quote_id, payload)
        if not updated:
            raise ValueError("Cotação não encontrada.")

        self.customer_repo.update(
            id=updated["customer_id"],
            attributes={"customer_state_now": status_value, "updated_at": datetime.utcnow()},
        )
        return updated

    def delete_quote(self, quote_id: str) -> bool:
        return self.quote_repo.delete(quote_id)
