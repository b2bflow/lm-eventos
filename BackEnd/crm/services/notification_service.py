"""Avisos automáticos da plataforma por WhatsApp (escrita formal, sem emoji).

Destinos vêm de LmSettings (com fallback para ERICA_PHONE). Se o destino não estiver
configurado, o aviso só vai para o log: nunca interrompe o fluxo que o gerou.
"""
import os

from crm.models.lm_settings_model import LmSettings
from utils.logger import logger


def card_link(customer_id: str) -> str:
    base = os.getenv("FRONTEND_URL", "").rstrip("/")
    return f"{base}/funil?lead={customer_id}" if base else f"/funil?lead={customer_id}"


def format_phone(phone: str | None) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) == 13 and digits.startswith("55"):
        return f"({digits[2:4]}) {digits[4:9]}-{digits[9:]}"
    return phone or ""


class NotificationService:
    def __init__(self, chat_client=None):
        self._chat = chat_client

    @property
    def chat(self):
        if self._chat is None:
            from gateway.adapters.zapi_adapter import ZAPIClient
            self._chat = ZAPIClient()
        return self._chat

    def _send(self, destination: str, text: str, purpose: str) -> bool:
        if not destination:
            logger.warning(f"[Notification] Destino de '{purpose}' não configurado. Aviso não enviado: {text!r}")
            return False
        try:
            return bool(self.chat.send_message(phone=destination, message=text))
        except Exception as e:
            logger.error(f"[Notification] Falha ao enviar '{purpose}': {e}")
            return False

    def erica_destination(self) -> str:
        cfg = LmSettings.get()
        return cfg.erica_phone or os.getenv("ERICA_PHONE", "")

    def notify_erica(self, text: str) -> bool:
        return self._send(self.erica_destination(), text, "erica")

    def notify_approval(self, text: str) -> bool:
        cfg = LmSettings.get()
        return self._send(cfg.approval_phone or self.erica_destination(), text, "aprovacao")

    def notify_sdr(self, text: str) -> bool:
        return self._send(LmSettings.get().sdr_phone, text, "sdr")

    def notify_lucia(self, text: str) -> bool:
        return self._send(LmSettings.get().lucia_phone, text, "lucia")

    def notify_ai_lead(self, customer) -> bool:
        """Aviso no grupo de atendimento: a IA qualificou um lead (reunião com o Marcelo, 28/10)."""
        return self._send(LmSettings.get().ai_leads_group, ai_lead_text(customer), "grupo_atendimento")


def _fmt_day(value) -> str | None:
    return value.strftime("%d/%m/%Y") if hasattr(value, "strftime") else (str(value) if value else None)


def ai_lead_text(customer) -> str:
    """Resumo do lead para o grupo (uma mensagem, uma informação por linha, sem emoji)."""
    from crm import domain
    get = (lambda key: customer.get(key)) if isinstance(customer, dict) else (lambda key: getattr(customer, key, None))
    rows = [
        ("Nome", get("name")),
        ("Telefone", format_phone(get("phone"))),
        ("Produto", domain.PRODUCTS.get(get("product") or "", None)),
        ("Evento", get("celebration_type") or get("event_title")),
        ("Data do evento", _fmt_day(get("event_date"))),
        ("Convidados", get("guest_count") or None),
        ("Local", get("venue")),
        ("Próximo passo", get("next_step")),
    ]
    lines = ["Novo lead qualificado pela IA"]
    lines += [f"{label}: {value}" for label, value in rows if value not in (None, "")]
    lines.append(f"Card: {card_link(str(get('id')))}")
    return "\n".join(lines)
