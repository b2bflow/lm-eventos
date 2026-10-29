"""Quem é o contato de um webhook da Z-API: número de telefone e identificador privado `@lid`.

O WhatsApp identifica alguns contatos por `<dígitos>@lid` em vez do número. No mesmo chat a Z-API
pode mandar o número em `phone` (mensagem recebida, com o lid em `senderLid`/`chatLid`) e o lid em
`phone` (mensagem enviada pelo celular da LM). Sem ligar os dois, a mesma pessoa virava dois
contatos e duas conversas. O lid conhecido fica em `Customer.whatsapp_lid`; para contatos antigos,
o lid é procurado nas mensagens recebidas (raw_metadata) e guardado na primeira vez.
"""
from chat.models.message_model import MessageModel
from crm.models.custumer_model import Customer
from gateway.adapters.zapi_adapter import ZAPIClient
from utils.logger import logger
from crm.phones import phone_variants


def payload_lids(data: dict) -> list[str]:
    """Lids do contato no payload. Em fromMe o senderLid é o da própria LM e fica de fora."""
    if data.get("isGroup"):
        return []
    keys = ("phone", "chatLid") if data.get("fromMe") else ("phone", "chatLid", "senderLid")
    lids = []
    for key in keys:
        value = str(data.get(key) or "").strip()
        if ZAPIClient.is_lid(value) and value not in lids:
            lids.append(value)
    return lids


def _by_lid_in_messages(lids: list[str]) -> Customer | None:
    """Contato com número cujas mensagens recebidas trouxeram esse lid (contatos de antes do campo)."""
    query = {"direction": "INCOMING", "$or": [
        {"raw_metadata.senderLid": {"$in": lids}}, {"raw_metadata.chatLid": {"$in": lids}},
    ]}
    for message in MessageModel.objects(__raw__=query).order_by("-created_at").limit(20):
        customer = message.customer
        if customer and not ZAPIClient.is_lid(customer.phone):
            return customer
    return None


def find_customer(phone: str, data: dict) -> Customer | None:
    """Contato do webhook. Prefere o cadastro com número; aprende o lid e, quando a mensagem traz
    o número de um contato que só existia pelo lid, troca o telefone dele pelo número."""
    lids = payload_lids(data)
    has_number = bool(phone) and not ZAPIClient.is_lid(phone)

    if has_number:
        customer = Customer.objects(phone__in=phone_variants(phone) or [phone]).order_by("created_at").first()
        if customer:
            return remember_lid(customer, lids)
    if not lids:
        return None

    known = list(Customer.objects(__raw__={"$or": [{"whatsapp_lid": {"$in": lids}}, {"phone": {"$in": lids}}]}))
    with_number = [c for c in known if not ZAPIClient.is_lid(c.phone)]
    if with_number:
        return remember_lid(with_number[0], lids)

    customer = _by_lid_in_messages(lids)
    if customer:
        return remember_lid(customer, lids)

    only_lid = known[0] if known else None
    if only_lid and has_number:
        # Primeira vez que esse contato aparece com o número: o cadastro passa a usar o número.
        logger.info(f"[WhatsAppIdentity] Contato {only_lid.id} trocou {only_lid.phone} pelo número {phone}.")
        only_lid.phone = phone
        only_lid.save()
    return remember_lid(only_lid, lids) if only_lid else None


def remember_lid(customer: Customer, lids: list[str]) -> Customer:
    if lids and not customer.whatsapp_lid:
        customer.whatsapp_lid = lids[0]
        Customer.objects(id=customer.id).update(set__whatsapp_lid=lids[0])
    return customer


def text_or_label(data: dict) -> str | None:
    """Texto do que a pessoa mandou, ou rótulo do tipo; None para avisos sem conteúdo (reação,
    figurinha, 'aguardando mensagem', chamada...), que não viram mensagem."""
    text = data.get("text")
    if isinstance(text, dict) and (text.get("message") or "").strip():
        return text["message"]
    location = data.get("location")
    if isinstance(location, dict):
        name = location.get("name") or location.get("address") or ""
        return f"[Localização] {name}".strip()
    contact = data.get("contact")
    if isinstance(contact, dict):
        return f"[Contato] {contact.get('displayName') or ''}".strip()
    if isinstance(data.get("audio"), dict):
        return "[Áudio]"
    return None
