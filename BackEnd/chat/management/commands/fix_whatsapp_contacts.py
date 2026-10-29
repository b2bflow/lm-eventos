"""Corrige dados que os webhooks da Z-API deixaram errados antes da correção de 29/10.

Sem --apply só mostra o que faria. Duas correções:

- contatos @lid duplicados: o celular da LM manda o lid em `phone`, o cliente manda o número, e a
  mesma pessoa virou dois contatos com duas conversas. As mensagens do contato "<dígitos>@lid" vão
  para a conversa do contato com número (o lid fica guardado nele) e o contato @lid é excluído.
  Só junta quando o lid aparece nas mensagens recebidas do contato com número. Contato @lid com
  dados de lead (funil, qualificação da IA, proposta, lead arquivado) fica para revisão manual.
- "Olá, Tenho interesse e queria mais informações, por favor." sem texto no payload: era o texto
  que a plataforma punha quando a mensagem não tinha texto. A maioria é áudio de cliente cuja
  transcrição falhou (de maio a 13/10): essas e as outras com conteúdo (vídeo, arquivo, localização,
  contato, mensagem de empresa) ficam com o rótulo certo ("[Áudio]"...). Só os avisos sem conteúdo
  (chamada, mensagem apagada, reação, "aguardando mensagem") são apagados.
"""
from django.core.management.base import BaseCommand

from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from chat.services.whatsapp_identity import _by_lid_in_messages, text_or_label
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
    help = "Junta contatos @lid duplicados e corrige as mensagens 'Olá, Tenho interesse' que não eram texto."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Grava as correções (sem ele, só mostra).")

    def handle(self, *args, **options):
        apply = options["apply"]
        prefix = "" if apply else "[simulação] "
        merged, review = self._merge_lid_contacts(apply, prefix)
        relabeled, removed = self._fix_placeholders(apply, prefix)
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}{merged} contato(s) @lid juntado(s), {review} para revisar à mão; "
            f"'Olá, Tenho interesse': {relabeled} com rótulo corrigido, {removed} aviso(s) apagado(s)."
            + ("" if apply else " Rode com --apply para gravar.")
        ))

    @staticmethod
    def _lead_data(customer: Customer) -> str | None:
        """Motivo para não excluir o contato @lid sozinho (ele tem dados de lead)."""
        from crm.models.opportunity_model import Opportunity
        from sales.models import Proposal
        if Proposal.objects(customer=customer).count():
            return "tem proposta"
        if Opportunity.objects(customer=customer).count():
            return "tem lead arquivado"
        if customer.funnel_entered_at or customer.ai_qualified_at:
            return "está no funil ou foi qualificado pela IA"
        return None

    def _merge_lid_contacts(self, apply: bool, prefix: str) -> tuple[int, int]:
        merged = review = 0
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
            reason = self._lead_data(lid_customer)
            if reason:
                review += 1
                self.stdout.write(self.style.WARNING(f"{prefix}revisar à mão ({reason}): {label}"))
                continue
            self.stdout.write(f"{prefix}juntar {label}")
            merged += 1
            if apply:
                self._merge(lid_customer, real, conversations)
        return merged, review

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

    def _fix_placeholders(self, apply: bool, prefix: str) -> tuple[int, int]:
        from chat.services.message_service import MessageService
        # Só com o payload salvo (raw_metadata.phone) e sem texto nele: mensagem antiga sem payload fica.
        query = {"direction": "INCOMING", "content": PLACEHOLDER,
                 "raw_metadata.phone": {"$exists": True}, "raw_metadata.text": {"$exists": False}}
        kinds: dict = {}
        to_delete, conversations = [], set()
        relabeled = 0
        for message in MessageModel.objects(__raw__=query).only("id", "conversation", "raw_metadata"):
            data = message.raw_metadata or {}
            label = None if data.get("waitingMessage") or data.get("notification") else text_or_label(data)
            kind = label.split("]")[0] + "]" if label and label.startswith("[") else (
                "apagar: " + (data.get("notification") or ("aguardando mensagem" if data.get("waitingMessage")
                                                          else "reação" if data.get("reaction") else "sem conteúdo")))
            kinds[kind] = kinds.get(kind, 0) + 1
            conversations.add(message.conversation.id if message.conversation else None)
            if not label:
                to_delete.append(message.id)
                continue
            relabeled += 1
            if apply:
                message_type, media_url = MessageService._extract_media(data)
                MessageModel.objects(id=message.id).update(set__content=label, set__message_type=message_type,
                                                          set__media_url=media_url)
        for kind, count in sorted(kinds.items(), key=lambda item: -item[1]):
            self.stdout.write(f"{prefix}{count} {kind}")
        if apply:
            if to_delete:
                MessageModel.objects(id__in=to_delete).delete()
            for conversation in ConversationModel.objects(id__in=[c for c in conversations if c]):
                _refresh_preview(conversation)
        return relabeled, len(to_delete)
