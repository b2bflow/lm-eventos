"""Tags (etiquetas) dos clientes.

GET    /crm/tags/[?counts=1]          catálogo (com quantos clientes têm cada tag)
POST   /crm/tags/ {name, color?}      cria (qualquer usuário); nome repetido devolve a existente (200)
PATCH  /crm/tags/<id>/ {name?, color?} renomeia ou troca a cor (só admin)
DELETE /crm/tags/<id>/                 exclui e tira dos clientes (só admin; as automáticas não saem)
PUT    /crm/contacts/<id>/tags/ {tags}  troca as tags do cliente (lista de chaves)
"""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from crm.services.customer_tag_service import CustomerTagService, TagNotFoundError
from users.permissions import has_role
from utils.logger import logger


def _handle(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except TagNotFoundError as nf:
            return Response({"detail": str(nf)}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[TagController] Falha em {fn.__name__}: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    wrapper.__name__ = fn.__name__
    return wrapper


def _admin_only(request):
    if not has_role(request.user):
        return Response({"detail": "Só a Erica (admin) renomeia, troca a cor ou exclui tags."},
                        status=status.HTTP_403_FORBIDDEN)
    return None


class TagListController(APIView):
    permission_classes = [IsAuthenticated]

    @_handle
    def get(self, request):
        with_counts = str(request.query_params.get("counts", "")).lower() in ("1", "true")
        return Response(CustomerTagService().list_tags(with_counts=with_counts))

    @_handle
    def post(self, request):
        tag, created = CustomerTagService().create_tag(
            request.data.get("name"), request.data.get("color"), user=request.user)
        return Response(tag, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class TagDetailController(APIView):
    permission_classes = [IsAuthenticated]

    @_handle
    def patch(self, request, tag_id):
        return _admin_only(request) or Response(CustomerTagService().update_tag(tag_id, request.data))

    @_handle
    def delete(self, request, tag_id):
        return _admin_only(request) or Response(CustomerTagService().delete_tag(tag_id))


class ContactTagsController(APIView):
    permission_classes = [IsAuthenticated]

    @_handle
    def put(self, request, contact_id):
        return Response(CustomerTagService().set_customer_tags(contact_id, request.data.get("tags"), user=request.user))
