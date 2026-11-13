"""Tags (etiquetas) dos clientes: catálogo com nome e cor, criado pela equipe.

O cliente guarda as chaves em `Customer.tags` (várias). A tag automática antiga, gravada pela IA e pelo
orçamento em `Customer.customer_custom_tag` ("visita tecnica", "operador humano", "orcamento"), continua
valendo e aparece junto: ver crm.services.customer_tag_service.customer_tag_keys.
"""
import re
import unicodedata
from datetime import datetime

from mongoengine import BooleanField, DateTimeField, Document, StringField

TAG_COLORS = ("slate", "red", "orange", "amber", "lime", "emerald", "teal", "sky", "blue", "violet", "pink")

# Tags gravadas sozinhas em Customer.customer_custom_tag. A chave é a mesma gravada lá.
BUILTIN_TAGS = {
    "visita tecnica": ("Visita técnica", "violet"),
    "operador humano": ("Operador humano", "blue"),
    "orcamento": ("Orçamento", "amber"),
}

NAME_MAX = 40


def tag_key(name) -> str:
    """Chave da tag: minúsculas, sem acento e sem pontuação ("Pós-venda!" -> "pos venda")."""
    text = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


class CustomerTag(Document):
    meta = {
        "collection": "customer_tags",
        "indexes": [{"fields": ["key"], "unique": True}],
        "strict": False,
    }

    key = StringField(required=True, max_length=60)
    name = StringField(required=True, max_length=NAME_MAX)
    color = StringField(choices=TAG_COLORS, default="slate")
    builtin = BooleanField(default=False)  # tag automática (IA/orçamento): não pode ser excluída
    created_at = DateTimeField(default=datetime.utcnow)
    created_by = StringField(null=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "key": self.key,
            "name": self.name,
            "color": self.color or "slate",
            "builtin": bool(self.builtin),
        }
