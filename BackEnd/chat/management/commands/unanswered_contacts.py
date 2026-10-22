"""Contatos que mandaram mensagem e ficaram sem resposta (investigação W3, reunião de 22/10).

Só lê o banco, não manda nada. Olha os últimos --days dias (padrão 14) e lista duas situações:

- sem resposta: a última mensagem do cliente veio depois da última que saiu para ele e já passou
  de --minutes (padrão 10). Pega falha da IA, do webhook ou do claim do menu de boas-vindas.
- @lid: contato que a Z-API identifica como "<dígitos>@lid". Até o commit 2a8b387 a resposta da IA
  para esses contatos ficava gravada no painel, mas o envio era recusado (telefone inválido); só o
  menu chegava. Toda resposta da IA anterior ao deploy da correção não chegou ao cliente.

Contatos de parceiro (operador humano) ficam de fora: a IA não atende esses contatos.
"""
import csv
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand

from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from crm.models.custumer_model import Customer
from crm.services.business_hours import to_local
from gateway.adapters.zapi_adapter import ZAPIClient

COLUMNS = ["situacao", "nome", "telefone", "atendimento", "conversa", "primeira_msg_cliente",
           "ultima_msg_cliente", "ultima_resposta", "respostas_ia"]


def _when(value: datetime | None) -> str:
    return to_local(value).strftime("%d/%m %H:%M") if value else "-"


class Command(BaseCommand):
    help = "Lista contatos que ficaram sem resposta (e contatos @lid que não receberam a resposta da IA)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=14, help="Quantos dias para trás olhar (padrão 14).")
        parser.add_argument("--minutes", type=int, default=10,
                            help="Tempo sem resposta para contar como sem resposta (padrão 10).")
        parser.add_argument("--csv", action="store_true", help="Saída em CSV (para planilha).")

    def handle(self, *args, **options):
        now = datetime.utcnow()
        since = now - timedelta(days=options["days"])
        deadline = now - timedelta(minutes=options["minutes"])

        stats: dict = {}
        messages = (MessageModel.objects(created_at__gte=since, direction__in=["INCOMING", "OUTGOING"])
                    .only("conversation", "direction", "created_at", "role", "hidden_from_ai").as_pymongo())
        for msg in messages:
            item = stats.setdefault(msg["conversation"], {"first_in": None, "last_in": None, "last_out": None,
                                                          "ai_out": 0})
            at = msg["created_at"]
            if msg["direction"] == "INCOMING":
                item["first_in"] = min(item["first_in"] or at, at)
                item["last_in"] = max(item["last_in"] or at, at)
            else:
                item["last_out"] = max(item["last_out"] or at, at)
                if msg.get("role") == "assistant" and not msg.get("hidden_from_ai"):
                    item["ai_out"] += 1

        conversations = {c.id: c for c in ConversationModel.objects(id__in=list(stats)).no_dereference()}
        customer_ids = {c.customer.id for c in conversations.values() if c.customer}
        customers = {c.id: c for c in Customer.objects(id__in=list(customer_ids), human_operator__ne=True)}

        rows = []
        for conversation_id, item in stats.items():
            conversation = conversations.get(conversation_id)
            customer = customers.get(conversation.customer.id) if conversation and conversation.customer else None
            if not customer:
                continue
            situations = []
            if item["last_in"] and item["last_in"] <= deadline and (not item["last_out"] or item["last_out"] < item["last_in"]):
                situations.append("sem resposta")
            if ZAPIClient.is_lid(customer.phone) and item["ai_out"]:
                situations.append("@lid")
            if situations:
                rows.append((item["last_in"] or since, [
                    " + ".join(situations), customer.name or "", customer.phone or "", conversation.tag or "",
                    str(conversation.id), _when(item["first_in"]), _when(item["last_in"]), _when(item["last_out"]),
                    str(item["ai_out"]),
                ]))
        rows = [row for _, row in sorted(rows, key=lambda r: r[0], reverse=True)]

        if options["csv"]:
            writer = csv.writer(self.stdout)
            writer.writerow(COLUMNS)
            writer.writerows(rows)
            return
        self.stdout.write(f"Últimos {options['days']} dias (horário de Brasília): {len(rows)} contato(s).")
        for row in rows:
            data = dict(zip(COLUMNS, row))
            self.stdout.write(
                f"- [{data['situacao']}] {data['nome'] or 'Sem nome'} ({data['telefone']}), {data['atendimento']}: "
                f"cliente {data['primeira_msg_cliente']} a {data['ultima_msg_cliente']}, "
                f"última resposta {data['ultima_resposta']}, {data['respostas_ia']} resposta(s) da IA. "
                f"Conversa {data['conversa']}")
