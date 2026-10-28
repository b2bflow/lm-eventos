"""Disponibilidade, reservas e movimentações de estoque.

Disponível no período = total - reservas ativas (reservado/retirado) que cruzam o período.
Reserva nasce quando a proposta é aceita e é liberada ao cancelar/recusar ou no retorno.
Também dá para reservar à mão na tela de estoque. Reserva é opcional
(LmSettings.inventory_reservations_enabled): desligada, nada reserva e o disponível é o total.
"""
import re
from collections import defaultdict
from datetime import datetime
from math import floor

import unicodedata

from bson import ObjectId

from inventory.models import (
    ACTIVE_RESERVATION_STATUSES, LINES, InventoryItem, InventoryKit, InventoryMovement, InventoryObservation,
    InventoryReservation, KitPiece,
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

    def _manual_target(self, start: datetime, end: datetime, client_name, customer_id, note):
        """Validações comuns da reserva manual (item ou kit). Devolve o lead, se informado."""
        if not self.reservations_enabled():
            raise ValueError("A reserva de estoque está desligada nas configurações.")
        if not all(isinstance(v, (str, type(None))) for v in (client_name, customer_id, note)):
            raise ValueError("Cliente, lead e observação devem ser texto.")
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
        return customer

    def reserve_manual(self, item: InventoryItem, qty, start: datetime, end: datetime, client_name: str | None = None,
                       customer_id: str | None = None, note: str | None = None, user=None) -> dict:
        """Reserva feita à mão na tela de estoque (sem proposta). Não deixa passar do disponível."""
        customer = self._manual_target(start, end, client_name, customer_id, note)
        qty = _positive_qty(qty)
        if not float(qty).is_integer() and not _fractional_item(item):
            raise ValueError(f"A quantidade de {item.name} precisa ser um número inteiro.")
        if not item.active:
            raise ValueError("Item removido do estoque.")
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
        """Cancela uma reserva manual ainda não retirada. As de proposta seguem o ciclo da proposta.
        Reserva de kit cancela todas as peças do kit juntas."""
        reservation = (InventoryReservation.objects(id=ObjectId(reservation_id)).first()
                       if ObjectId.is_valid(reservation_id) else None)
        if reservation is None:
            raise LookupError("Reserva não encontrada.")
        if reservation.proposal_id:
            raise ValueError("Reserva de proposta: cancele ou recuse a proposta para liberar.")
        if reservation.status != 'reservado':
            raise ValueError(f"Reserva {reservation.status} não pode ser cancelada.")
        if reservation.group_id:
            InventoryReservation.objects(group_id=reservation.group_id, status='reservado').update(
                set__status='cancelado')
            reservation.reload()
            return reservation.to_dict()
        reservation.status = 'cancelado'
        reservation.save()
        return reservation.to_dict()

    # --- Kits ------------------------------------------------------------------------------

    @staticmethod
    def ensure_builtin_kits() -> None:
        """Cria os kits das faixas de som e do som de cerimônia (os que a calculadora escolhe sozinha),
        com as peças que valem hoje (catálogo + LmSettings.price_table). Idempotente."""
        from crm.models.lm_settings_model import LmSettings
        from sales.catalog import CATALOG_BY_CODE, SOUND_SET_CODES, merge_price_table

        existing = set(InventoryKit.objects(code__in=list(SOUND_SET_CODES)).distinct('code'))
        missing = [code for code in SOUND_SET_CODES if code not in existing and code in CATALOG_BY_CODE]
        if not missing:
            return
        sets = merge_price_table(LmSettings.get().price_table)["sound_sets"]
        for code in missing:
            item = CATALOG_BY_CODE[code]
            pieces = [KitPiece(code=p["code"], qty=float(p["qty"])) for p in sets.get(code) or []]
            InventoryKit(code=code, name=item["name"], line=item["line"], description=item.get("note"),
                         pieces=pieces, builtin=True).save()

    def kits(self, start: datetime | None = None, end: datetime | None = None,
             include_inactive: bool = False) -> list[dict]:
        """Kits com preço, peças e quantos dá para montar no período (pela peça que acaba primeiro)."""
        self.ensure_builtin_kits()
        queryset = InventoryKit.objects() if include_inactive else InventoryKit.objects(active=True)
        from sales.catalog import SOUND_SET_CODES
        # Faixas de som na ordem do público; depois os kits criados, por linha e nome
        order = {code: i for i, code in enumerate(SOUND_SET_CODES)}
        kits = sorted(queryset, key=lambda k: (not k.builtin, order.get(k.code, 0), k.line, _normalize(k.name)))
        codes = {p.code for kit in kits for p in kit.pieces}
        items = {i.code: i for i in InventoryItem.objects(code__in=list(codes))}
        with_reservations = bool(start and end) and self.reservations_enabled()
        reserved = self.reserved_qty(start, end, [i.id for i in items.values()]) if with_reservations else {}
        from sales.services.pricing_service import effective_price_table
        table = effective_price_table()
        return [self._kit_dict(kit, items, reserved, table) for kit in kits]

    def kit(self, kit: InventoryKit, start: datetime | None = None, end: datetime | None = None) -> dict:
        items = {i.code: i for i in InventoryItem.objects(code__in=[p.code for p in kit.pieces])}
        with_reservations = bool(start and end) and self.reservations_enabled()
        reserved = self.reserved_qty(start, end, [i.id for i in items.values()]) if with_reservations else {}
        from sales.services.pricing_service import effective_price_table
        data = self._kit_dict(kit, items, reserved, effective_price_table())
        # Reservas manuais do kit: uma por grupo (a quantidade de kits sai da primeira peça)
        groups = {}
        for r in InventoryReservation.objects(kit_code=kit.code, status__in=ACTIVE_RESERVATION_STATUSES,
                                              end__gt=datetime.utcnow()).order_by('start'):
            if r.group_id not in groups:
                per_kit = next((p.qty for p in kit.pieces if p.code == r.item.code), None)
                groups[r.group_id] = {**r.to_dict(), "kits": round(r.qty / per_kit) if per_kit else None}
        data["reservations"] = list(groups.values())
        return data

    @staticmethod
    def _kit_dict(kit: InventoryKit, items: dict, reserved: dict, table: dict) -> dict:
        from sales.catalog import COMPONENT_NAMES
        from sales.services.quote_calculator import unit_price
        data = kit.to_dict()
        try:
            price = unit_price(kit.code, table)
        except ValueError:
            price = None
        data["sale_price"] = float(price) if price is not None else None
        pieces, buildable, limiting, problems = [], None, None, []
        for piece in kit.pieces:
            item = items.get(piece.code)
            row = {"code": piece.code, "qty": piece.qty, "item_id": str(item.id) if item else None,
                   "name": COMPONENT_NAMES.get(piece.code, item.name) if item else piece.code, "unit": item.billing_unit if item else None,
                   "active": bool(item and item.active), "owned": bool(item and item.owned),
                   "qty_total": item.qty_total if item else None, "available": None}
            if not item or not item.active:
                problems.append(f"{row['name']} foi removido do estoque")
            elif item.owned and item.qty_total is not None:
                row["available"] = item.qty_total - reserved.get(item.id, 0)
                fits = max(0, floor(row["available"] / piece.qty)) if piece.qty else 0
                if buildable is None or fits < buildable:
                    buildable, limiting = fits, row["name"]
            pieces.append(row)
        data.update(pieces=pieces, buildable=buildable, limiting_piece=limiting, problems=problems)
        if not kit.pieces and kit.builtin:
            problems.append("Sem peças: sai no PDF pelo nome")
        return data

    @staticmethod
    def _kit_code(name: str) -> str:
        from sales.catalog import CATALOG_BY_CODE
        base = unicodedata.normalize("NFKD", f"kit {name}").encode("ascii", "ignore").decode().lower()
        base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")[:60] or "kit"
        code, n = base, 2
        while code in CATALOG_BY_CODE or InventoryKit.objects(code=code).first() or InventoryItem.objects(code=code).first():
            code, n = f"{base}_{n}", n + 1
        return code

    @staticmethod
    def _kit_pieces(raw, builtin: bool) -> list[KitPiece]:
        """[{code, qty}] -> peças válidas: itens ativos do estoque (kit não entra em kit), quantidade
        positiva (inteira, salvo m²/metro); o mesmo item repetido soma."""
        from sales.catalog import SOUND_SET_CODES
        if not isinstance(raw, list):
            raise ValueError("Peças inválidas.")
        totals: dict[str, float] = {}
        for entry in raw:
            if not isinstance(entry, dict) or not isinstance(entry.get("code"), str):
                raise ValueError("Peças inválidas.")
            code = entry["code"]
            if code in SOUND_SET_CODES or InventoryKit.objects(code=code).first():
                raise ValueError("Um kit não pode ter outro kit como peça.")
            item = InventoryItem.objects(code=code).first()
            if not item or not item.active:
                raise ValueError(f"Item {code} não está no estoque.")
            qty = _positive_qty(entry.get("qty"))
            if not qty.is_integer() and not _fractional_item(item):
                raise ValueError(f"A quantidade de {item.name} precisa ser um número inteiro.")
            totals[code] = totals.get(code, 0) + qty
        if not totals and not builtin:
            raise ValueError("Adicione ao menos uma peça ao kit.")
        return [KitPiece(code=code, qty=qty) for code, qty in totals.items()]

    def save_kit(self, kit: InventoryKit | None, data: dict, user=None) -> InventoryKit:
        """Cria (kit=None) ou edita um kit. Kit das faixas de som (builtin) só muda peças, descrição e
        como sai no PDF: o nome e a linha são os da calculadora."""
        if not isinstance(data, dict):
            raise ValueError("Corpo inválido.")
        for key in ("name", "description", "line"):
            if key in data and not isinstance(data[key], (str, type(None))):
                raise ValueError("Nome, linha e descrição devem ser texto.")
        if "show_pieces" in data and not isinstance(data["show_pieces"], bool):
            raise ValueError("Opção do PDF inválida.")
        builtin = bool(kit and kit.builtin)
        if kit is None:
            kit = InventoryKit(builtin=False)
            user_id, user_name = _user_info(user)
            kit.created_by, kit.created_by_name = user_id, user_name
            if "pieces" not in data:
                raise ValueError("Adicione ao menos uma peça ao kit.")
        if not builtin:
            if "name" in data or kit.id is None:
                name = (data.get("name") or "").strip()
                if not name:
                    raise ValueError("Informe o nome do kit.")
                duplicate = InventoryKit.objects(name__iexact=name, active=True, id__ne=kit.id).first()
                if duplicate:
                    raise ValueError(f"Já existe um kit chamado {duplicate.name}.")
                kit.name = name[:120]
            if "line" in data or kit.id is None:
                if data.get("line") not in LINES:
                    raise ValueError("Informe uma linha válida.")
                kit.line = data["line"]
        if "pieces" in data:
            kit.pieces = self._kit_pieces(data["pieces"], builtin)
        if "description" in data:
            kit.description = (data["description"] or "").strip()[:2000] or None
        if "show_pieces" in data:
            kit.show_pieces = data["show_pieces"]
        if "active" in data:
            if builtin and data["active"] is not True:
                raise ValueError("As faixas de som são usadas pela calculadora: dá para mudar as peças, não remover.")
            kit.active = bool(data["active"])
        if not kit.code:
            kit.code = self._kit_code(kit.name)
        kit.updated_at = datetime.utcnow()
        kit.save()
        return kit

    def kits_with_item(self, item: InventoryItem, active_only: bool = True) -> list[dict]:
        queryset = InventoryKit.objects(pieces__code=item.code)
        if active_only:
            queryset = queryset.filter(active=True)
        return [{"id": str(k.id), "name": k.name, "qty": next(p.qty for p in k.pieces if p.code == item.code)}
                for k in queryset]

    def reserve_kit(self, kit: InventoryKit, qty, start: datetime, end: datetime, client_name: str | None = None,
                    customer_id: str | None = None, note: str | None = None, user=None) -> list[dict]:
        """Reserva manual de N kits: uma reserva por peça, no mesmo grupo (cancela tudo junto). Confere
        todas as peças antes de reservar qualquer uma."""
        customer = self._manual_target(start, end, client_name, customer_id, note)
        qty = _positive_qty(qty)
        if not qty.is_integer():
            raise ValueError("A quantidade de kits precisa ser um número inteiro.")
        if not kit.active:
            raise ValueError("Kit removido.")
        if not kit.pieces:
            raise ValueError("Kit sem peças: nada para reservar.")
        items = {i.code: i for i in InventoryItem.objects(code__in=[p.code for p in kit.pieces])}
        reserved = self.reserved_qty(start, end, [i.id for i in items.values()])
        shortages = []
        for piece in kit.pieces:
            item = items.get(piece.code)
            if not item or not item.active:
                raise ValueError(f"{item.name if item else piece.code} foi removido do estoque: ajuste o kit.")
            if item.owned and item.qty_total is not None:
                available = item.qty_total - reserved.get(item.id, 0)
                if piece.qty * qty > available:
                    shortages.append(f"{item.name}: precisa {piece.qty * qty:g}, disponível {available:g}")
        if shortages:
            raise ValueError("Falta peça no período. " + "; ".join(shortages) + ".")
        user_id, user_name = _user_info(user)
        group_id = str(ObjectId())
        label = f"{qty:g} x {kit.name}"
        created = [InventoryReservation(
            item=items[piece.code], proposal_id=None, customer=customer,
            client_name=(client_name or "").strip() or None, qty=piece.qty * qty, start=start, end=end,
            note=(note or "").strip() or None, group_id=group_id, kit_code=kit.code, kit_name=kit.name,
            created_by=user_id,
            created_by_name=user_name,
        ).save() for piece in kit.pieces]
        return [{**r.to_dict(), "kit_label": label} for r in created]

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
        data["kits"] = self.kits_with_item(item)
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
