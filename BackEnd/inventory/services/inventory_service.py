"""Disponibilidade, reservas e movimentações de estoque.

Disponível no período = total - reservas ativas (reservado/retirado) que cruzam o período.
Reserva nasce quando a proposta é aceita e é liberada ao cancelar/recusar ou no retorno.
Também dá para reservar à mão na tela de estoque. Reserva é opcional
(LmSettings.inventory_reservations_enabled): desligada, nada reserva e o disponível é o total.
"""
from collections import defaultdict
from datetime import datetime

import unicodedata

from bson import ObjectId

from inventory.models import (
    ACTIVE_RESERVATION_STATUSES, InventoryItem, InventoryMovement, InventoryObservation, InventoryReservation,
)


def _normalize(text: str) -> str:
    """Minúsculas e sem acento, para a busca por nome ("iluminacao" acha "Iluminação")."""
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def _user_info(user) -> tuple[str | None, str | None]:
    if user is None or not getattr(user, 'id', None):
        return None, None
    name = (getattr(user, 'first_name', '') or '').strip() or getattr(user, 'username', None)
    return str(user.id), name


def _fractional_item(item) -> bool:
    """Mesma regra da calculadora: só m² e metro corrido (passa-cabo) aceitam fração; torre é peça."""
    from sales.catalog import CATALOG_BY_CODE
    from sales.services.quote_calculator import FRACTIONAL_UNITS
    if (CATALOG_BY_CODE.get(item.code) or {}).get("billed_length_m"):
        return False
    return item.billing_unit in FRACTIONAL_UNITS


def _positive_qty(qty) -> float:
    if isinstance(qty, bool):
        raise ValueError("Informe a quantidade.")
    try:
        qty = float(qty)
    except (TypeError, ValueError):
        raise ValueError("Informe a quantidade.")
    if not qty > 0 or qty == float("inf"):
        raise ValueError("Informe a quantidade.")
    return qty


class InventoryService:

    @staticmethod
    def reservations_enabled() -> bool:
        from crm.models.lm_settings_model import LmSettings
        return bool(getattr(LmSettings.get(), 'inventory_reservations_enabled', True))

    def reserved_qty(self, start: datetime, end: datetime, item_ids=None, exclude_proposal: str | None = None) -> dict:
        """{item_id: quantidade reservada} das reservas ativas que cruzam [start, end)."""
        if not self.reservations_enabled():
            return {}
        queryset = InventoryReservation.objects(status__in=ACTIVE_RESERVATION_STATUSES, start__lt=end, end__gt=start)
        if item_ids is not None:
            queryset = queryset.filter(item__in=list(item_ids))
        if exclude_proposal:
            queryset = queryset.filter(proposal_id__ne=exclude_proposal)
        totals = defaultdict(float)
        for reservation in queryset.only('item', 'qty').as_pymongo():
            totals[reservation['item']] += reservation['qty']
        return totals

    def availability(self, codes, start: datetime, end: datetime, exclude_proposal: str | None = None) -> dict:
        """{code: disponível} para a calculadora. None = item não contado ou terceirizado (só aviso)."""
        items = {item.code: item for item in InventoryItem.objects(code__in=list(codes))}
        reserved = self.reserved_qty(start, end, [i.id for i in items.values()], exclude_proposal)
        result = {}
        for code in codes:
            item = items.get(code)
            if item is None:
                continue
            if not item.owned or item.qty_total is None:
                result[code] = None
            else:
                result[code] = item.qty_total - reserved.get(item.id, 0)
        return result

    def list_with_availability(self, line: str | None = None, start: datetime | None = None,
                               end: datetime | None = None, include_inactive: bool = False,
                               search: str | None = None) -> list[dict]:
        from sales.services.pricing_service import effective_price_table
        from sales.services.quote_calculator import unit_price

        # Faixas e conjuntos de som não são itens: o estoque mostra as peças (caixas, microfones...)
        from sales.catalog import SOUND_SET_CODES
        queryset = InventoryItem.objects(code__nin=list(SOUND_SET_CODES))
        if not include_inactive:
            queryset = queryset.filter(active=True)
        if line:
            queryset = queryset.filter(line=line)
        items = list(queryset.order_by('line', 'name'))
        if search:
            terms = _normalize(search).split()
            items = [i for i in items if all(t in _normalize(f"{i.name} {i.code} {i.size or ''} {i.line}") for t in terms)]
        with_reservations = bool(start and end) and self.reservations_enabled()
        reserved = self.reserved_qty(start, end, [i.id for i in items]) if with_reservations else {}
        table = effective_price_table()
        result = []
        for item in items:
            data = item.to_dict()
            try:
                price = unit_price(item.code, table)
            except ValueError:
                price = None
            data["sale_price"] = float(price) if price is not None else None
            data["reserved"] = reserved.get(item.id, 0) if with_reservations else None
            if item.qty_total is None or not item.owned:
                data["available"] = None
            else:
                data["available"] = item.qty_total - reserved.get(item.id, 0)
            result.append(data)
        return result

    # --- Reservas ------------------------------------------------------------------------

    def reserve(self, proposal_id: str, customer, lines: list[dict], start: datetime, end: datetime) -> list:
        """Reserva os itens próprios e contados das linhas da proposta (idempotente por proposta).
        Com a reserva desligada nas configurações, não reserva nada."""
        self.release(proposal_id)
        if not self.reservations_enabled():
            return []
        # Conjunto de som reserva as peças (caixas, microfones...), não o conjunto
        lines = [piece for line in lines for piece in (
            [{"code": c["code"], "qty": float(c["qty"]) * float(line.get("qty") or 1)} for c in line["components"]]
            if line.get("components") else [line])]
        items = {i.code: i for i in InventoryItem.objects(code__in=[l["code"] for l in lines])}
        created = []
        for line in lines:
            item = items.get(line["code"])
            if not item or not item.owned or item.qty_total is None:
                continue
            created.append(InventoryReservation(
                item=item, proposal_id=proposal_id, customer=customer, qty=float(line["qty"]), start=start, end=end,
            ).save())
        return created

    def release(self, proposal_id: str) -> int:
        return InventoryReservation.objects(proposal_id=proposal_id, status='reservado').update(set__status='cancelado')

    def reservations(self, proposal_id: str | None = None, status: str | None = None, item=None,
                     active_only: bool = False) -> list[dict]:
        queryset = InventoryReservation.objects()
        if proposal_id:
            queryset = queryset.filter(proposal_id=proposal_id)
        if status:
            queryset = queryset.filter(status=status)
        if item is not None:
            queryset = queryset.filter(item=item)
        if active_only:
            queryset = queryset.filter(status__in=ACTIVE_RESERVATION_STATUSES)
        return [r.to_dict() for r in queryset.order_by('start')]

    def reserve_manual(self, item: InventoryItem, qty, start: datetime, end: datetime, client_name: str | None = None,
                       customer_id: str | None = None, note: str | None = None, user=None) -> dict:
        """Reserva feita à mão na tela de estoque (sem proposta). Não deixa passar do disponível."""
        if not self.reservations_enabled():
            raise ValueError("A reserva de estoque está desligada nas configurações.")
        if not all(isinstance(v, (str, type(None))) for v in (client_name, customer_id, note)):
            raise ValueError("Cliente, lead e observação devem ser texto.")
        qty = _positive_qty(qty)
        if not float(qty).is_integer() and not _fractional_item(item):
            raise ValueError(f"A quantidade de {item.name} precisa ser um número inteiro.")
        if not item.active:
            raise ValueError("Item removido do estoque.")
        if end <= start:
            raise ValueError("O fim do período deve ser depois do início.")
        customer = None
        if customer_id:
            from crm.models.custumer_model import Customer
            customer = Customer.objects(id=ObjectId(customer_id)).first() if ObjectId.is_valid(customer_id) else None
            if customer is None:
                raise ValueError("Lead inválido.")
        if not (client_name or "").strip() and customer is None:
            raise ValueError("Informe para quem é a reserva.")
        if item.owned and item.qty_total is not None:
            available = item.qty_total - self.reserved_qty(start, end, [item.id]).get(item.id, 0)
            if qty > available:
                raise ValueError(f"Só há {available:g} disponível(is) de {item.name} no período.")
        user_id, user_name = _user_info(user)
        reservation = InventoryReservation(
            item=item, proposal_id=None, customer=customer, client_name=(client_name or "").strip() or None,
            qty=qty, start=start, end=end, note=(note or "").strip() or None, created_by=user_id,
            created_by_name=user_name,
        ).save()
        return reservation.to_dict()

    def cancel_manual(self, reservation_id: str) -> dict:
        """Cancela uma reserva manual ainda não retirada. As de proposta seguem o ciclo da proposta."""
        reservation = (InventoryReservation.objects(id=ObjectId(reservation_id)).first()
                       if ObjectId.is_valid(reservation_id) else None)
        if reservation is None:
            raise LookupError("Reserva não encontrada.")
        if reservation.proposal_id:
            raise ValueError("Reserva de proposta: cancele ou recuse a proposta para liberar.")
        if reservation.status != 'reservado':
            raise ValueError(f"Reserva {reservation.status} não pode ser cancelada.")
        reservation.status = 'cancelado'
        reservation.save()
        return reservation.to_dict()

    # --- Ficha do item ---------------------------------------------------------------------

    def item_detail(self, item: InventoryItem) -> dict:
        now = datetime.utcnow()
        data = item.to_dict(with_observations=True)
        from sales.services.pricing_service import effective_price_table
        from sales.services.quote_calculator import unit_price
        try:
            price = unit_price(item.code, effective_price_table())
        except ValueError:
            price = None
        data["sale_price"] = float(price) if price is not None else None
        data["reservations"] = [r.to_dict() for r in InventoryReservation.objects(
            item=item, status__in=ACTIVE_RESERVATION_STATUSES, end__gt=now).order_by('start')]
        data["movements"] = [m.to_dict() for m in InventoryMovement.objects(item=item).order_by('-date').limit(30)]
        data["reservations_enabled"] = self.reservations_enabled()
        return data

    def add_observation(self, item: InventoryItem, text, user=None, kind: str = 'nota') -> dict:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Escreva a observação.")
        user_id, user_name = _user_info(user)
        observation = InventoryObservation(kind=kind, text=text.strip()[:2000], author_id=user_id,
                                           author_name=user_name)
        InventoryItem.objects(id=item.id).update_one(push__observations=observation,
                                                     set__updated_at=datetime.utcnow())
        return observation.to_dict()

    def remove_observation(self, item: InventoryItem, observation_id: str) -> bool:
        if not ObjectId.is_valid(observation_id):
            return False
        return bool(InventoryItem.objects(id=item.id).update_one(
            pull__observations__id=ObjectId(observation_id)))

    def adjust_quantity(self, item: InventoryItem, delta, reason, user=None) -> dict:
        """Entrada (delta > 0) ou baixa (delta < 0) de peças, com o motivo registrado na ficha."""
        if isinstance(delta, bool) or not isinstance(delta, int) or delta == 0:
            raise ValueError("Informe quantas peças entram (positivo) ou saem (negativo).")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Informe o motivo do ajuste.")
        if not item.owned:
            raise ValueError("Item terceirizado não tem quantidade em estoque.")
        current = item.qty_total or 0
        if current + delta < 0:
            raise ValueError(f"Baixa maior que o total ({current}).")
        item.qty_total = current + delta
        item.counted_at = datetime.utcnow()
        item.approximate_count = False
        item.updated_at = datetime.utcnow()
        item.save()
        verb = "Entrada" if delta > 0 else "Baixa"
        self.add_observation(item, f"{verb} de {abs(delta)} (total {current} → {item.qty_total}): {reason.strip()}",
                             user=user, kind='ajuste')
        item.reload()
        return item.to_dict()

    # --- Movimentações (Lúcia) -------------------------------------------------------------

    def register_movement(self, code: str, qty: float, movement_type: str, customer_id: str | None = None,
                          proposal_id: str | None = None, user=None, note: str | None = None) -> dict:
        if movement_type not in ('saida', 'retorno'):
            raise ValueError("Tipo de movimentação inválido (saida ou retorno).")
        # Ids chegam do JSON: só texto (um objeto viraria operador do Mongo, ex. {"$ne": null}).
        if not isinstance(code, str) or not all(isinstance(v, (str, type(None))) for v in (customer_id, proposal_id)):
            raise ValueError("Item, lead e proposta devem ser informados como texto.")
        if customer_id and not ObjectId.is_valid(customer_id):
            raise ValueError("Lead inválido.")
        qty = _positive_qty(qty)
        item = InventoryItem.objects(code=code).first()
        if not item:
            raise ValueError("Item não encontrado.")
        from crm.models.custumer_model import Customer
        customer = Customer.objects(id=ObjectId(customer_id)).first() if customer_id else None
        movement = InventoryMovement(
            item=item, customer=customer, proposal_id=proposal_id, qty=float(qty), type=movement_type,
            registered_by=str(user.id) if user is not None and getattr(user, 'id', None) else None, note=note,
        ).save()
        if proposal_id:
            new_status = 'retirado' if movement_type == 'saida' else 'devolvido'
            from_status = 'reservado' if movement_type == 'saida' else 'retirado'
            InventoryReservation.objects(proposal_id=proposal_id, item=item, status=from_status).update(set__status=new_status)
        return movement.to_dict()
