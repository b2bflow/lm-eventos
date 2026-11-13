"""Tags (etiquetas) dos clientes: catálogo (criar, renomear, trocar a cor, excluir) e as tags de cada cliente.

O cliente pode ter várias tags. As escolhidas pela equipe ficam em `Customer.tags`; a automática (IA e
orçamento) continua em `Customer.customer_custom_tag`, que a IA troca sozinha. Tirar a automática à mão
limpa esse campo; a IA pode gravá-la de novo depois.
"""
from datetime import datetime

from bson import ObjectId
from mongoengine.errors import NotUniqueError
from mongoengine.queryset.visitor import Q

from crm.models.custumer_model import Customer
from crm.models.customer_tag_model import BUILTIN_TAGS, NAME_MAX, TAG_COLORS, CustomerTag, tag_key
from crm.repositories.log_service_repository import ServiceLogRepository

MAX_TAGS = 200  # no catálogo
MAX_TAGS_PER_CUSTOMER = 20


class TagNotFoundError(ValueError):
    pass


def _operator(user) -> str | None:
    return str(user.id) if user is not None and getattr(user, "id", None) else None


def ensure_builtin_tags() -> None:
    """Põe no catálogo as tags automáticas que ainda não estão lá (nome e cor padrão)."""
    existing = set(CustomerTag.objects(key__in=list(BUILTIN_TAGS)).scalar("key"))
    for key, (name, color) in BUILTIN_TAGS.items():
        if key not in existing:
            try:
                CustomerTag(key=key, name=name, color=color, builtin=True).save()
            except NotUniqueError:  # outra requisição criou ao mesmo tempo
                pass


def customers_with_tag(key: str):
    """Clientes com a tag, escolhida pela equipe ou automática."""
    return Customer.objects(Q(tags=key) | Q(customer_custom_tag=key))


def customer_ids_with_tag(key: str) -> list:
    return list(customers_with_tag(key).scalar("id"))


def _get_tag(tag_id: str) -> CustomerTag:
    try:
        tag = CustomerTag.objects(id=ObjectId(tag_id)).first()
    except Exception:
        tag = None
    if not tag:
        raise TagNotFoundError("Tag não encontrada.")
    return tag


def _clean_name(name) -> tuple[str, str]:
    name = " ".join(str(name or "").split())
    if not name:
        raise ValueError("Informe o nome da tag.")
    if len(name) > NAME_MAX:
        raise ValueError(f"Nome da tag com mais de {NAME_MAX} caracteres.")
    key = tag_key(name)
    if not key:
        raise ValueError("Use letras ou números no nome da tag.")
    return name, key


def _same_name(key: str, exclude_id=None) -> CustomerTag | None:
    """Tag com o mesmo nome (pela chave ou pelo nome atual, já que renomear não muda a chave)."""
    for tag in CustomerTag.objects(id__ne=exclude_id) if exclude_id else CustomerTag.objects():
        if tag.key == key or tag_key(tag.name) == key:
            return tag
    return None


def _clean_color(color) -> str | None:
    if color in (None, ""):
        return None
    if color not in TAG_COLORS:
        raise ValueError(f"Cor inválida: {color}.")
    return color


class CustomerTagService:

    # --- Catálogo ---------------------------------------------------------------------------

    def list_tags(self, with_counts: bool = False) -> list[dict]:
        ensure_builtin_tags()
        tags = sorted(CustomerTag.objects(), key=lambda t: t.key)
        result = [t.to_dict() for t in tags]
        if with_counts:
            for item in result:
                item["count"] = customers_with_tag(item["key"]).count()
        return result

    def create_tag(self, name, color=None, user=None) -> tuple[dict, bool]:
        """Cria a tag. Se já existe uma com o mesmo nome (sem acento/maiúscula), devolve ela (created=False)."""
        ensure_builtin_tags()
        name, key = _clean_name(name)
        existing = _same_name(key)
        if existing:
            return existing.to_dict(), False
        if CustomerTag.objects.count() >= MAX_TAGS:
            raise ValueError(f"Limite de {MAX_TAGS} tags. Exclua alguma antes de criar outra.")
        color = _clean_color(color) or TAG_COLORS[CustomerTag.objects.count() % len(TAG_COLORS)]
        try:
            tag = CustomerTag(key=key, name=name, color=color, created_by=_operator(user)).save()
        except NotUniqueError:  # criada ao mesmo tempo por outra pessoa
            return CustomerTag.objects.get(key=key).to_dict(), False
        return tag.to_dict(), True

    def update_tag(self, tag_id: str, data: dict) -> dict:
        """Renomeia ou troca a cor. A chave não muda (os clientes continuam com a tag)."""
        tag = _get_tag(tag_id)
        if "name" in data:
            name, key = _clean_name(data.get("name"))
            other = _same_name(key, exclude_id=tag.id)
            if other:
                raise ValueError(f"Já existe a tag {other.name}.")
            tag.name = name
        if "color" in data:
            tag.color = _clean_color(data.get("color")) or "slate"
        tag.save()
        return tag.to_dict()

    def delete_tag(self, tag_id: str) -> dict:
        """Exclui a tag e tira ela de todos os clientes. As automáticas não saem (a IA usa)."""
        tag = _get_tag(tag_id)
        if tag.builtin:
            raise ValueError("Esta tag é colocada automaticamente pela IA e não pode ser excluída.")
        removed = Customer.objects(tags=tag.key).update(pull__tags=tag.key)
        tag.delete()
        return {"removed_from": removed}

    # --- Tags do cliente --------------------------------------------------------------------

    def set_customer_tags(self, customer_id: str, keys, user=None) -> dict:
        """Troca as tags do cliente pela lista enviada (chaves do catálogo) e registra na linha do tempo."""
        try:
            customer = Customer.objects(id=ObjectId(customer_id)).first()
        except Exception:
            customer = None
        if not customer:
            raise ValueError("Contato não encontrado.")
        if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
            raise ValueError("Envie as tags como lista.")
        wanted = list(dict.fromkeys(k.strip() for k in keys if k and k.strip()))
        if len(wanted) > MAX_TAGS_PER_CUSTOMER:
            raise ValueError(f"No máximo {MAX_TAGS_PER_CUSTOMER} tags por contato.")
        ensure_builtin_tags()
        catalog = {t.key: t for t in CustomerTag.objects(key__in=wanted)}
        unknown = [k for k in wanted if k not in catalog]
        if unknown:
            raise ValueError(f"Tag não encontrada: {unknown[0]}.")

        before = customer.tag_keys
        auto = customer.customer_custom_tag
        # A automática fica no campo dela (a IA continua trocando); as demais, nas tags da equipe.
        customer.customer_custom_tag = auto if auto in wanted else None
        customer.tags = [k for k in wanted if k != customer.customer_custom_tag]
        after = customer.tag_keys
        added = [k for k in after if k not in before]
        removed = [k for k in before if k not in after]
        if added or removed:
            customer.updated_at = datetime.utcnow()
            customer.save()
            names = {t.key: t.name for t in CustomerTag.objects(key__in=added + removed)}
            parts = [f"+ {names.get(k, k)}" for k in added] + [f"− {names.get(k, k)}" for k in removed]
            ServiceLogRepository.create_log(
                customer=customer, operator_id=_operator(user), action_type="TAGS_CHANGED",
                description="Tags: " + ", ".join(parts) + ".",
                metadata={"added": added, "removed": removed},
            )
        return {"id": str(customer.id), "tags": after}
