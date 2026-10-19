"""Paginação por cursor (data + id) para listas que mudam de ordem enquanto o usuário rola.

Com página numérica, uma conversa que recebe mensagem sobe para o topo e desloca as páginas
(itens repetidos ou pulados). O cursor guarda a posição do último item entregue; a próxima
página começa estritamente depois dele, na mesma ordenação decrescente.
"""
import base64
from datetime import datetime

from bson import ObjectId
from mongoengine.queryset.visitor import Q


def encode_cursor(ts: datetime, obj_id) -> str:
    raw = f"{ts.isoformat()}|{obj_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str | None) -> tuple[datetime, ObjectId] | None:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts, obj_id = raw.split("|", 1)
        return datetime.fromisoformat(ts), ObjectId(obj_id)
    except Exception:
        raise ValueError("Cursor inválido.")


def parse_page_size(value, default: int, maximum: int) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(size, maximum))


def paginate_desc(queryset, field: str, cursor: str | None, page_size: int) -> tuple[list, str | None]:
    """Página em ordem decrescente de (field, id). Devolve (itens, próximo cursor ou None)."""
    position = decode_cursor(cursor)
    if position:
        ts, obj_id = position
        queryset = queryset.filter(
            Q(**{f"{field}__lt": ts}) | (Q(**{field: ts}) & Q(id__lt=obj_id))
        )
    items = list(queryset.order_by(f"-{field}", "-id").limit(page_size + 1))
    has_more = len(items) > page_size
    items = items[:page_size]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(getattr(last, field), last.id)
    return items, next_cursor
