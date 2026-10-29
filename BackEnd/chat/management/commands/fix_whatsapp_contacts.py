"""Corrige dados que os webhooks da Z-API deixaram errados antes da correção de 29/10.

Sem --apply só mostra o que faria. Duas correções:

- contatos @lid duplicados: o celular da LM manda o lid em `phone`, o cliente manda o número, e a
  mesma pessoa virou dois contatos com duas conversas. As mensagens do contato "<dígitos>@lid" vão
  para a conversa do contato com número (o lid fica guardado nele) e o contato @lid é excluído.
  Só junta quando o lid aparece nas mensagens recebidas do contato com número; contato @lid com
  proposta fica para revisão manual.
- "Olá, Tenho interesse e queria mais informações, por favor." sem texto no payload: era o texto
  que a plataforma colocava em avisos sem conteúdo (aguardando mensagem, reação, chamada). Essas
  mensagens são apagadas.
"""
from django.core.management.base import BaseCommand

from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from chat.services.whatsapp_identity import _by_lid_in_messages
from crm.models.custumer_model import Customer
from gateway.adapters.zapi_adapter import ZAPIClient

PLACEHOLDER = "Olá, Tenho interesse e queria mais informações, por favor."
TAKEOVER_TEXT = "Mensagens enviadas direto pelo WhatsApp juntadas a esta conversa. Atendimento com operador."


def _refresh_preview(conversation: ConversationModel) -> None:
    from chat.services.message_service import MessageService
    last = MessageModel.objects(conversation=conversation, direction__ne="INTERNAL").order_by("-created_at").first()
    conversation.last_message_content = (
        MessageService._preview(last.content, last.message_type, last.raw_metadata) if last else ""
    )
    if last:
        conversation.updated_at = max(conversation.updated_at or last.created_at, last.created_at)
    conversation.save()


class Command(BaseCommand):
    help = "Junta contatos @lid duplicados e apaga as mensagens 'Olá, Tenho interesse' geradas por avisos sem conteúdo."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Grava as correções (sem ele, só mostra).")

    def handle(self, *args, **options):
        apply = options["apply"]
        prefix = "" if apply else "[simulação] "
        merged = self._merge_lid_contacts(apply, prefix)
        removed = self._remove_placeholders(apply, prefix)
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}{merged} contato(s) @lid juntado(s); {removed} mensagem(ns) 'Olá, Tenho interesse' apagada(s)."
            + ("" if apply else " Rode com --apply para gravar.")
        ))

    def _merge_lid_contacts(self, apply: bool, prefix: str) -> int:
        from sales.models import Proposal
        merged = 0
        for lid_customer in Customer.objects(phone__endswith="@lid"):
            lid = lid_customer.phone
            if not ZAPIClient.is_lid(lid):
                continue
            real = Customer.objects(whatsapp_lid=lid, phone__ne=lid).first() or _by_lid_in_messages([lid])
            if not real or real.id == lid_customer.id:
                continue
            conversations = list(ConversationModel.objects(customer=lid_customer).order_by("created_at"))
            count = MessageModel.objects(conversation__in=conversations).count() if conversations else 0
            label = f"{lid_customer.name or lid} ({lid}) -> {real.name or real.phone} ({real.phone}): {count} mensagem(ns)"
            if Proposal.objects(customer=lid_customer).count():
                self.stdout.write(self.style.WARNING(f"{prefix}revisar à mão, contato @lid tem proposta: {label}"))
                continue
            self.stdout.write(f"{prefix}juntar {label}")
            merged += 1
            if apply:
                self._merge(lid_customer, real, conversations)
        return merged

    def _merge(self, lid_customer: Customer, real: Customer, conversations: list[ConversationModel]) -> None:
        from chat.container import ChatContainer
        from crm.container import CrmContainer
        target = (ConversationModel.objects(customer=real, status__in=["OPEN", "IN_PROGRESS"]).first()
                  or ConversationModel.objects(customer=real).order_by("-updated_at").first())
        moved_from_phone = False
        for conversation in conversations:
            messages = MessageModel.objects(conversation=conversation)
            moved_from_phone = moved_from_phone or bool(messages.filter(raw_metadata__sent_from_phone=True).count())
            if target:
                messages.update(set__conversation=target, set__customer=real)
                conversation.delete()
            else:
                messages.update(set__customer=real)
                conversation.customer = real
                # O orçamento era do contato @lid, que vai ser excluído: a conversa pega o do contato com número.
                conversation.quote = None
                conversation.save()
                target = conversation

        Customer.objects(id=real.id).update(set__whatsapp_lid=lid_customer.phone)
        CrmContainer.get_contact_service().delete(str(lid_customer.id))
        if target:
            target.reload()
            _refresh_preview(target)
            if moved_from_phone and (target.ai_active or target.tag == "AGENTE"):
                ChatContainer.get_handover_service().take_over(target, TAKEOVER_TEXT)

    def _remove_placeholders(self, apply: bool, prefix: str) -> int:
        # Só com o payload salvo (raw_metadata.phone) e sem texto nele: mensagem antiga sem payload fica.
        query = {"direction": "INCOMING", "content": PLACEHOLDER,
                 "raw_metadata.phone": {"$exists": True}, "raw_metadata.text": {"$exists": False}}
        messages = MessageModel.objects(__raw__=query)
        total = messages.count()
        by_conversation: dict = {}
        for message in messages.only("conversation"):
            by_conversation.setdefault(message.conversation, 0)
            by_conversation[message.conversation] += 1
        for conversation, count in sorted(by_conversation.items(), key=lambda item: -item[1]):
            customer = conversation.customer
            self.stdout.write(f"{prefix}apagar {count} 'Olá, Tenho interesse' de {customer.name if customer else '?'} "
                              f"({customer.phone if customer else '?'})")
        if apply and total:
            messages.delete()
            for conversation in by_conversation:
                _refresh_preview(conversation)
        return total
