"""Coloca no funil ("Pediu orçamento") quem clicou em "Solicitar orçamento" antes dessa regra existir.

Reunião com o Marcelo (19/11): todo cliente que clica no botão de orçamento entra no funil, mesmo
que pare de responder antes de a IA terminar a qualificação. A regra vale para os cliques novos
(`crm.services.funnel_entry.mark_quote_requested`); este comando aplica aos cliques desde uma data.

Só mexe em lead em aberto: lead encerrado (ganho ou perdido) ou de antes do funil zerado fica como
está e aparece em "ignorados". Lead que já está no funil não muda de etapa (só ganha a marca do
pedido, que conta no filtro "Orçamentos IA" do WhatsApp). Sem --apply só mostra o que faria.

    python manage.py backfill_quote_requests --since 2026-11-01
    python manage.py backfill_quote_requests --since 2026-11-01 --apply
"""
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from mongoengine.queryset.visitor import Q

from crm import domain
from crm.models.custumer_model import Customer
from crm.services.funnel_entry import _OUT_OF_FUNNEL_TYPES, mark_quote_requested

# Botão "Solicitar orçamento" do menu de boas-vindas (chat.services.message_service)
QUOTE_BUTTON_ID = "1"


def _classify(customer: Customer) -> str:
    """O que o mark_quote_requested(reopen=False) faria com o contato."""
    if (customer.human_operator or getattr(customer, "whatsapp_group", False)
            or (customer.contact_type or "lead") in _OUT_OF_FUNNEL_TYPES):
        return "fora"
    closed = customer.stage in (domain.CONTRACT_SIGNED, domain.LOST)
    stale = customer.funnel_entered_at is None and bool(customer.product or customer.stage != domain.NEW_LEAD)
    if closed or stale:
        return "skipped"
    return "marked" if customer.funnel_entered_at else "entered"


class Command(BaseCommand):
    help = "Coloca no funil (\"Pediu orçamento\") quem clicou em \"Solicitar orçamento\" desde uma data."

    def add_arguments(self, parser):
        parser.add_argument("--since", required=True, help="Data inicial dos cliques (AAAA-MM-DD, horário de Brasília).")
        parser.add_argument("--apply", action="store_true", help="Grava. Sem isso só mostra o que faria.")

    def handle(self, *args, **options):
        from chat.models.message_model import MessageModel
        try:
            # Meia-noite de Brasília (UTC-3) em UTC, como o resto do banco
            since = datetime.strptime(options["since"], "%Y-%m-%d") + timedelta(hours=3)
        except ValueError:
            raise CommandError("--since precisa ser uma data AAAA-MM-DD.")
        apply = options["apply"]

        clicks = MessageModel.objects(
            Q(raw_metadata__buttonsResponseMessage__buttonId=QUOTE_BUTTON_ID)
            | Q(content__contains=f"'buttonId': '{QUOTE_BUTTON_ID}'"),
            direction="INCOMING", created_at__gte=since,
        ).no_dereference().only("customer", "created_at")
        last_click = {}
        for message in clicks:
            customer_id = getattr(message.customer, "id", message.customer)
            if customer_id and (customer_id not in last_click or message.created_at > last_click[customer_id]):
                last_click[customer_id] = message.created_at

        counts = {"entered": 0, "marked": 0, "skipped": 0, "fora": 0, "ja_marcado": 0, "lead_novo": 0}
        entered = []
        for customer in Customer.objects(id__in=list(last_click)):
            clicked_at = last_click[customer.id]
            if customer.quote_requested_at:
                counts["ja_marcado"] += 1
                continue
            # Clique de um lead anterior do contato (o lead atual começou depois)
            if customer.lead_started_at and clicked_at < customer.lead_started_at:
                counts["lead_novo"] += 1
                continue
            kind = _classify(customer)
            if apply and kind in ("entered", "marked"):
                kind = mark_quote_requested(customer, now=clicked_at, reopen=False) or "fora"
            counts[kind] += 1
            if kind == "entered":
                entered.append(f"{customer.name or '(sem nome)'} ({customer.phone})")

        verb = "Entraram" if apply else "Entrariam"
        self.stdout.write(f"Cliques em \"Solicitar orçamento\" desde {options['since']}: {len(last_click)} contato(s).")
        self.stdout.write(f"{verb} no funil em \"Pediu orçamento\": {counts['entered']}")
        for line in entered:
            self.stdout.write(f"  - {line}")
        self.stdout.write(f"Já no funil (só ganham a marca do pedido): {counts['marked']}")
        self.stdout.write(f"Ignorados, lead encerrado ou de antes do funil zerado: {counts['skipped']}")
        self.stdout.write(f"Ignorados, parceiro/fornecedor/candidato/grupo: {counts['fora']}")
        self.stdout.write(f"Ignorados, já marcados: {counts['ja_marcado']}; clique de um lead anterior: {counts['lead_novo']}")
        if not apply:
            self.stdout.write(self.style.WARNING("Nada gravado. Rode de novo com --apply para gravar."))
