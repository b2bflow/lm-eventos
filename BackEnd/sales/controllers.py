from bson import ObjectId
from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from crm.models.lm_settings_model import LmSettings
from crm.services.pipeline_service import PermissionDeniedError
from sales.catalog import CATALOG, LINES, OPERATIONAL_COSTS, SOCIAL_BASIC_PACKAGE
from sales.services.pricing_service import effective_price_table
from sales.services.proposal_service import ProposalService, valid_pdf_token
from sales.services.quote_calculator import unit_price
from utils.logger import logger

service = ProposalService()


def _handle(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except PermissionDeniedError as pe:
            return Response({"detail": str(pe)}, status=status.HTTP_403_FORBIDDEN)
        except (ValueError, TypeError) as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[Sales] Erro em {fn.__name__}: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    wrapper.__name__ = fn.__name__
    return wrapper


class CatalogController(APIView):
    """GET /sales/catalog/: itens com preço efetivo, custos operacionais e níveis de margem."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        table = effective_price_table()
        cfg = LmSettings.get()
        items = []
        for item in CATALOG:
            if not item["rentable"]:
                continue
            price = unit_price(item["code"], table)
            items.append({**item, "sale_price": float(price) if price is not None else None})
        return Response({
            "lines": LINES,
            "items": items,
            "operational_costs": [
                {"code": k, "label": v["label"], "price": table["operational_costs"].get(k, v["price"])}
                for k, v in OPERATIONAL_COSTS.items()
            ],
            "margin_levels": cfg.margin_levels,
            "invoice_rate": cfg.invoice_rate,
            "approval_ceiling": cfg.approval_ceiling,
            "proposal_validity_days": cfg.proposal_validity_days,
            "sound_tiers": table["sound_tiers"],
            "kits": [{"code": k, "label": v["label"], "pieces": v["pieces"]} for k, v in table["kits"].items()],
            "social_basic_package": SOCIAL_BASIC_PACKAGE,
            "social_max_guests": cfg.social_max_guests,
            "social_max_total": cfg.social_max_total,
        })


class CalculateController(APIView):
    """POST /sales/proposals/calculate/ {mode, inputs, customer_id?, replaces?}: prévia sem salvar."""
    permission_classes = [IsAuthenticated]

    @_handle
    def post(self, request):
        from crm.models.custumer_model import Customer
        customer_id = request.data.get("customer_id")
        if customer_id and not (isinstance(customer_id, str) and ObjectId.is_valid(customer_id)):
            raise ValueError("Lead inválido.")
        customer = Customer.objects(id=customer_id).first() if customer_id else None
        result, start, end = service.calculate(request.data.get("mode"), request.data.get("inputs") or {}, customer,
                                               exclude_proposal=request.data.get("replaces"))
        return Response({**result.to_dict(), "period_start": start.isoformat(), "period_end": end.isoformat()})


class ProposalListController(APIView):
    """GET /sales/proposals/?customer=<id> | ?status=aguardando_aprovacao. POST cria nova versão."""
    permission_classes = [IsAuthenticated]

    @_handle
    def get(self, request):
        if request.query_params.get("status") == "aguardando_aprovacao":
            return Response(service.pending_approvals())
        customer_id = request.query_params.get("customer")
        if not customer_id:
            return Response({"detail": "Informe o lead (customer)."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(service.list_for_customer(customer_id))

    @_handle
    def post(self, request):
        proposal = service.save(
            request.data.get("customer_id"), request.data.get("mode"), request.data.get("inputs") or {},
            user=request.user, replaces=request.data.get("replaces"),
        )
        return Response(proposal, status=status.HTTP_201_CREATED)


class ProposalDetailController(APIView):
    permission_classes = [IsAuthenticated]

    @_handle
    def get(self, request, proposal_id):
        from sales.services.proposal_service import _proposal
        return Response(_proposal(proposal_id).to_dict())


class ProposalActionController(APIView):
    """POST /sales/proposals/<id>/<approve|send|send-whatsapp|accept|reject>/."""
    permission_classes = [IsAuthenticated]

    @_handle
    def post(self, request, proposal_id, action):
        if action == "approve":
            return Response(service.decide(proposal_id, bool(request.data.get("approve", True)), user=request.user,
                                           note=request.data.get("note")))
        if action == "send":
            return Response(service.send(proposal_id, user=request.user))
        if action == "send-whatsapp":
            return Response(service.send_whatsapp(proposal_id, user=request.user))
        if action == "accept":
            return Response(service.accept(proposal_id, user=request.user))
        if action == "reject":
            return Response(service.reject(proposal_id, user=request.user, note=request.data.get("note")))
        return Response({"detail": "Ação inválida."}, status=status.HTTP_404_NOT_FOUND)


class ProposalPdfController(APIView):
    """GET /sales/proposals/<id>/pdf/[<nome>.pdf]: PDF da proposta. Exige login ou o link assinado (?t=).

    `?download=1` baixa em vez de abrir no navegador.
    """
    permission_classes = [AllowAny]

    def get(self, request, proposal_id, file_name=None):
        if not (request.user and request.user.is_authenticated) and not valid_pdf_token(proposal_id, request.query_params.get("t")):
            return Response({"detail": "Link inválido ou expirado."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            content, name = service.pdf(proposal_id)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_404_NOT_FOUND)
        disposition = "attachment" if request.query_params.get("download") else "inline"
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'{disposition}; filename="{name}"'
        # O painel mostra o PDF num iframe (aba WhatsApp e card): libera o enquadramento só para as
        # origens do painel (X-Frame-Options DENY bloqueava a prévia).
        response.xframe_options_exempt = True
        ancestors = " ".join(["'self'", *_panel_origins()])
        response["Content-Security-Policy"] = f"frame-ancestors {ancestors}"
        response["Cache-Control"] = "private, no-store"
        return response


def _panel_origins() -> list[str]:
    import os
    origins = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    front = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
    return sorted({o for o in origins + ([front] if front else []) if o.startswith(("http://", "https://"))})
