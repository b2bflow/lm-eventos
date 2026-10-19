from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from crm.container import CrmContainer
from crm.services.contact_service import DuplicateContactError
from crm.services.pipeline_service import PermissionDeniedError
from users.permissions import B2BFLOW, has_role
from utils.logger import logger


def _bool_param(value):
    if value in (None, ""):
        return None
    return str(value).lower() in ("1", "true", "sim", "yes")


def _handle(fn):
    """400 (regra), 409 (telefone já cadastrado, com o id do contato existente), 500 (inesperado)."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except DuplicateContactError as dup:
            return Response({"detail": str(dup), "existing_id": dup.existing_id}, status=status.HTTP_409_CONFLICT)
        except PermissionDeniedError as pe:
            return Response({"detail": str(pe)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[ContactController] Falha em {fn.__name__}: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    wrapper.__name__ = fn.__name__
    return wrapper


class ContactListController(APIView):
    """GET /crm/contacts/?search=&contact_type=&owner=&partner=&page=&page_size= e POST (cria)."""
    permission_classes = [IsAuthenticated]

    @_handle
    def get(self, request):
        params = request.query_params
        page = max(int(params.get("page", 1) or 1), 1)
        page_size = min(max(int(params.get("page_size", 30) or 30), 1), 100)
        results, total = CrmContainer.get_contact_service().list_contacts(
            offset=(page - 1) * page_size, limit=page_size, search=params.get("search"),
            contact_type=params.get("contact_type") or None, owner=params.get("owner") or None,
            partner=_bool_param(params.get("partner")),
        )
        return Response({"count": total, "page": page, "page_size": page_size,
                         "has_more": page * page_size < total, "results": results})

    @_handle
    def post(self, request):
        contact = CrmContainer.get_contact_service().create(request.data, user=request.user)
        return Response(contact, status=status.HTTP_201_CREATED)


class ContactDetailController(APIView):
    """GET /crm/contacts/<id>/ (contato, leads, propostas e anexos) e PATCH (dados do contato)."""
    permission_classes = [IsAuthenticated]

    @_handle
    def get(self, request, contact_id):
        return Response(CrmContainer.get_contact_service().detail(contact_id))

    @_handle
    def patch(self, request, contact_id):
        return Response(CrmContainer.get_contact_service().update(contact_id, request.data, user=request.user))


class ContactNewLeadController(APIView):
    """POST /crm/contacts/<id>/new-lead/ {product}: abre um lead novo (o encerrado vai para o histórico)."""
    permission_classes = [IsAuthenticated]

    @_handle
    def post(self, request, contact_id):
        return Response(CrmContainer.get_contact_service().start_new_lead(
            contact_id, request.data.get("product"), user=request.user))


class ContactTimelineController(APIView):
    """GET /crm/contacts/<id>/timeline/?lead=<id da oportunidade | current>."""
    permission_classes = [IsAuthenticated]

    @_handle
    def get(self, request, contact_id):
        return Response(CrmContainer.get_contact_service().lead_timeline(contact_id, request.query_params.get("lead")))


class ContactImportController(APIView):
    """POST /crm/contacts/import-partners/ (multipart `file` ou JSON `content`; `dry_run` para conferir).

    Só admin (Erica) ou b2bflow."""
    permission_classes = [IsAuthenticated]

    @_handle
    def post(self, request):
        if not has_role(request.user, B2BFLOW):
            return Response({"detail": "Só a Erica (admin) ou a b2bflow importam a lista de parceiros."},
                            status=status.HTTP_403_FORBIDDEN)
        upload = request.FILES.get("file")
        if upload:
            if upload.size > 2 * 1024 * 1024:
                raise ValueError("Arquivo maior que 2 MB.")
            raw = upload.read()
            try:
                content = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                content = raw.decode("latin-1")  # CSV salvo pelo Excel em português
        else:
            content = request.data.get("content") or ""
        if not content.strip():
            raise ValueError("Envie um arquivo CSV com os telefones.")
        result = CrmContainer.get_contact_service().import_partners(
            content, user=request.user, dry_run=bool(_bool_param(request.data.get("dry_run"))))
        return Response(result)
