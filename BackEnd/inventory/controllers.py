import re
import unicodedata
from datetime import datetime, timedelta

from bson import ObjectId
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from inventory.models import BILLING_UNITS, LINES, InventoryItem, InventoryMovement, InventoryReservation
from inventory.services.inventory_service import InventoryService
from sales.services.pricing_service import set_item_price
from users.permissions import PORTA, has_role

service = InventoryService()

EDITABLE = ("line", "name", "size", "billing_unit", "qty_total", "owned", "rentable", "active", "note", "description")
TEXT_FIELDS = ("name", "size", "note", "description")


def _period(params):
    """start/end (YYYY-MM-DD); end inclusivo. Sem datas, não desconta reservas."""
    start, end = params.get("start"), params.get("end")
    if not start:
        return None, None
    start_dt = datetime.strptime(start[:10], "%Y-%m-%d")
    end_dt = datetime.strptime((end or start)[:10], "%Y-%m-%d") + timedelta(days=1)
    if end_dt <= start_dt:
        raise ValueError("O fim do período deve ser depois do início.")
    return start_dt, end_dt


def _can_edit(user) -> bool:
    return has_role(user, PORTA)


FORBIDDEN = "Só admin ou a Lúcia editam o estoque."
PRICE_FORBIDDEN = "Só a Erica (admin) define preços."


def _price_value(data):
    """`sale_price` do corpo: None limpa (volta ao preço padrão); número >= 0 grava. ValueError se inválido."""
    value = data.get("sale_price")
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("Preço inválido.")
    try:
        price = float(str(value).replace(",", "."))
    except ValueError:
        raise ValueError("Preço inválido.")
    if price < 0 or price != price or price in (float("inf"), float("-inf")):
        raise ValueError("O preço não pode ser negativo.")
    return round(price, 2)


def _item(item_id):
    return InventoryItem.objects(id=ObjectId(item_id)).first() if ObjectId.is_valid(item_id) else None


def _new_code(name: str, line: str) -> str:
    """Código a partir da linha + nome (ex.: "Iluminação" + "Moving head" -> iluminacao_moving_head)."""
    base = unicodedata.normalize("NFKD", f"{line} {name}").encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")[:60] or "item"
    code, n = base, 2
    while InventoryItem.objects(code=code).first():
        code, n = f"{base}_{n}", n + 1
    return code


def _invalid_text(data) -> bool:
    return any(k in data and not isinstance(data[k], (str, type(None))) for k in TEXT_FIELDS)


class InventoryItemsController(APIView):
    """GET /inventory/items/?line=&start=&end=&include_inactive=&q=. POST cria (admin ou porta);
    sem código, gera um a partir da linha e do nome."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            start, end = _period(request.query_params)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(service.list_with_availability(
            line=request.query_params.get("line") or None, start=start, end=end,
            include_inactive=request.query_params.get("include_inactive") in ("1", "true"),
            search=(request.query_params.get("q") or "").strip() or None,
        ))

    def post(self, request):
        if not _can_edit(request.user):
            return Response({"detail": FORBIDDEN}, status=status.HTTP_403_FORBIDDEN)
        data = request.data
        if not isinstance(data.get("code", ""), (str, type(None))) or not isinstance(data.get("name"), str) \
                or _invalid_text(data):
            return Response({"detail": "Informe código e nome em texto."}, status=status.HTTP_400_BAD_REQUEST)
        if not data["name"].strip() or data.get("line") not in LINES:
            return Response({"detail": "Informe nome e linha válidos."}, status=status.HTTP_400_BAD_REQUEST)
        qty = data.get("qty_total")
        if qty is not None and (isinstance(qty, bool) or not isinstance(qty, int) or qty < 0):
            return Response({"detail": "Quantidade total deve ser um número inteiro maior ou igual a zero."},
                            status=status.HTTP_400_BAD_REQUEST)
        code = (data.get("code") or "").strip() or _new_code(data["name"], data["line"])
        if InventoryItem.objects(code=code).first():
            return Response({"detail": "Já existe um item com esse código."}, status=status.HTTP_400_BAD_REQUEST)
        if data.get("billing_unit") and data["billing_unit"] not in BILLING_UNITS:
            return Response({"detail": "Unidade de cobrança inválida."}, status=status.HTTP_400_BAD_REQUEST)
        price = None
        if data.get("sale_price") not in (None, ""):
            if not has_role(request.user):
                return Response({"detail": PRICE_FORBIDDEN}, status=status.HTTP_403_FORBIDDEN)
            try:
                price = _price_value(data)
            except ValueError as e:
                return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        fields = {k: data[k] for k in EDITABLE if k in data}
        fields["name"] = data["name"].strip()
        try:
            item = InventoryItem(code=code, approximate_count=False, counted_at=datetime.utcnow(), **fields).save()
        except Exception as e:
            return Response({"detail": f"Dados inválidos: {e}"}, status=status.HTTP_400_BAD_REQUEST)
        if price is not None:
            set_item_price(item.code, price)
        return Response(item.to_dict(), status=status.HTTP_201_CREATED)


class InventoryItemDetailController(APIView):
    """GET ficha (observações, reservas ativas, últimas movimentações). PATCH edita. DELETE remove
    do estoque (desativa e mantém o histórico); ?permanent=1 apaga de vez, só sem histórico."""
    permission_classes = [IsAuthenticated]

    def get(self, request, item_id):
        item = _item(item_id)
        if not item:
            return Response({"detail": "Item não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response(service.item_detail(item))

    def patch(self, request, item_id):
        """Edita o item. `sale_price` (só admin) grava o preço de venda na tabela de preços;
        null volta ao preço padrão do catálogo."""
        if not _can_edit(request.user):
            return Response({"detail": FORBIDDEN}, status=status.HTTP_403_FORBIDDEN)
        item = _item(item_id)
        if not item:
            return Response({"detail": "Item não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        price_given = "sale_price" in request.data
        if price_given:
            if not has_role(request.user):
                return Response({"detail": PRICE_FORBIDDEN}, status=status.HTTP_403_FORBIDDEN)
            try:
                price = _price_value(request.data)
            except ValueError as e:
                return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        if _invalid_text(request.data):
            return Response({"detail": "Nome, tamanho e textos devem ser texto."}, status=status.HTTP_400_BAD_REQUEST)
        qty = request.data.get("qty_total")
        if qty is not None and (isinstance(qty, bool) or not isinstance(qty, (int, float)) or qty < 0):
            return Response({"detail": "Quantidade total deve ser um número maior ou igual a zero."},
                            status=status.HTTP_400_BAD_REQUEST)
        previous_qty = item.qty_total
        for key in EDITABLE:
            if key in request.data:
                setattr(item, key, request.data[key])
        if "qty_total" in request.data:
            item.counted_at = datetime.utcnow()
            item.approximate_count = False
        item.updated_at = datetime.utcnow()
        try:
            item.save()
        except Exception as e:
            return Response({"detail": f"Dados inválidos: {e}"}, status=status.HTTP_400_BAD_REQUEST)
        if price_given:
            set_item_price(item.code, price)
        if "qty_total" in request.data and item.qty_total != previous_qty:
            service.add_observation(item, f"Contagem corrigida: {previous_qty if previous_qty is not None else 'não contado'}"
                                          f" → {item.qty_total if item.qty_total is not None else 'não contado'}",
                                    user=request.user, kind="ajuste")
        return Response(item.to_dict())

    def delete(self, request, item_id):
        if not _can_edit(request.user):
            return Response({"detail": FORBIDDEN}, status=status.HTTP_403_FORBIDDEN)
        item = _item(item_id)
        if not item:
            return Response({"detail": "Item não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        if request.query_params.get("permanent") in ("1", "true"):
            if InventoryReservation.objects(item=item).first() or InventoryMovement.objects(item=item).first():
                return Response({"detail": "Item com reservas ou movimentações: só dá para remover (desativar)."},
                                status=status.HTTP_400_BAD_REQUEST)
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        InventoryItem.objects(id=item.id).update(set__active=False, set__updated_at=datetime.utcnow())
        return Response(status=status.HTTP_204_NO_CONTENT)


class InventoryItemAdjustController(APIView):
    """POST /inventory/items/<id>/adjust/ {delta: int, reason}: entrada ou baixa de peças."""
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        if not _can_edit(request.user):
            return Response({"detail": FORBIDDEN}, status=status.HTTP_403_FORBIDDEN)
        item = _item(item_id)
        if not item:
            return Response({"detail": "Item não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        try:
            return Response(service.adjust_quantity(item, request.data.get("delta"), request.data.get("reason"),
                                                    user=request.user))
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InventoryObservationsController(APIView):
    """POST /inventory/items/<id>/observations/ {text}: qualquer usuário anota sobre o equipamento.
    DELETE .../observations/<obs_id>/: autor da observação, admin ou porta."""
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        item = _item(item_id)
        if not item:
            return Response({"detail": "Item não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        try:
            return Response(service.add_observation(item, request.data.get("text"), user=request.user),
                            status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, item_id, observation_id):
        item = _item(item_id)
        observation = next((o for o in (item.observations if item else []) if str(o.id) == observation_id), None)
        if not observation:
            return Response({"detail": "Observação não encontrada."}, status=status.HTTP_404_NOT_FOUND)
        if observation.author_id != str(request.user.id) and not _can_edit(request.user):
            return Response({"detail": "Só quem escreveu, admin ou a Lúcia apagam a observação."},
                            status=status.HTTP_403_FORBIDDEN)
        if observation.kind == "ajuste":
            return Response({"detail": "Registro de ajuste de quantidade não pode ser apagado."},
                            status=status.HTTP_400_BAD_REQUEST)
        service.remove_observation(item, observation_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AvailabilityController(APIView):
    """GET /inventory/availability/?codes=a,b&start=YYYY-MM-DD&end=YYYY-MM-DD."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            start, end = _period(request.query_params)
            if not start:
                raise ValueError("Informe o período (start e end).")
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        codes = [c for c in (request.query_params.get("codes") or "").split(",") if c]
        return Response(service.availability(codes, start, end))


class ReservationsController(APIView):
    """GET ?proposal=&status=&item=&active=1. POST reserva manual
    {item_id, qty, start, end (YYYY-MM-DD, fim inclusivo), client_name | customer_id, note}."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        item_id = request.query_params.get("item")
        item = _item(item_id) if item_id else None
        if item_id and not item:
            return Response({"detail": "Item não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response(service.reservations(proposal_id=request.query_params.get("proposal"),
                                             status=request.query_params.get("status"), item=item,
                                             active_only=request.query_params.get("active") in ("1", "true")))

    def post(self, request):
        data = request.data
        item = _item(data.get("item_id")) if isinstance(data.get("item_id"), str) else None
        if not item:
            return Response({"detail": "Item não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        try:
            if not isinstance(data.get("start"), str) or not isinstance(data.get("end", ""), (str, type(None))):
                raise ValueError("Informe o período.")
            start, end = _period(data)
            reservation = service.reserve_manual(item, data.get("qty"), start, end, client_name=data.get("client_name"),
                                                 customer_id=data.get("customer_id"), note=data.get("note"),
                                                 user=request.user)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(reservation, status=status.HTTP_201_CREATED)


class ReservationDetailController(APIView):
    """DELETE /inventory/reservations/<id>/: cancela reserva manual (quem criou, admin ou porta)."""
    permission_classes = [IsAuthenticated]

    def delete(self, request, reservation_id):
        reservation = (InventoryReservation.objects(id=ObjectId(reservation_id)).first()
                       if ObjectId.is_valid(reservation_id) else None)
        if not reservation:
            return Response({"detail": "Reserva não encontrada."}, status=status.HTTP_404_NOT_FOUND)
        if reservation.created_by != str(request.user.id) and not _can_edit(request.user):
            return Response({"detail": "Só quem reservou, admin ou a Lúcia cancelam a reserva."},
                            status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(service.cancel_manual(reservation_id))
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class MovementsController(APIView):
    """GET lista; POST {code, qty, type: saida|retorno, customer_id, proposal_id, note} (admin ou porta)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        movements = InventoryMovement.objects().order_by("-date").limit(200)
        return Response([m.to_dict() for m in movements])

    def post(self, request):
        if not _can_edit(request.user):
            return Response({"detail": "Só admin ou a Lúcia registram movimentações."}, status=status.HTTP_403_FORBIDDEN)
        data = request.data
        try:
            movement = service.register_movement(data.get("code"), data.get("qty"), data.get("type"),
                                                 customer_id=data.get("customer_id"), proposal_id=data.get("proposal_id"),
                                                 user=request.user, note=data.get("note"))
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(movement, status=status.HTTP_201_CREATED)
