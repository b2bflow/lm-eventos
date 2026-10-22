from utils.logger import logger
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
import hmac
import os
from rest_framework.permissions import BasePermission, IsAuthenticated
from crm.container import CrmContainer
from crm.serializers import CustomerDTO
from crm.services.pipeline_service import PermissionDeniedError
from crm.services.customer_service import CustomerService
from crm.services.contact_service import DuplicateContactError
from users.permissions import has_role


def _duplicate(dup: DuplicateContactError) -> Response:
    return Response({"detail": str(dup), "existing_id": dup.existing_id}, status=status.HTTP_409_CONFLICT)


def _card_action(fn):
    """Trata erros comuns das ações do card: 400 (regra), 403 (papel), 500 (inesperado)."""
    def wrapper(self, request, pk=None):
        try:
            return fn(self, request, pk)
        except PermissionDeniedError as pe:
            return Response({"detail": str(pe)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[CustomerController] Falha em {fn.__name__} do lead {pk}: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


class CronOrAuthenticated(BasePermission):
    """Usuário logado ou agendador externo com o cabeçalho X-Cron-Token (env CRON_TOKEN).

    O follow-up automático dispara mensagens de WhatsApp para clientes: não pode ficar aberto.
    Sem CRON_TOKEN configurado, só usuário logado.
    """

    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return True
        expected = os.getenv("CRON_TOKEN", "")
        received = request.headers.get("X-Cron-Token", "")
        return bool(expected) and hmac.compare_digest(received.encode("utf-8"), expected.encode("utf-8"))


class CustomerController(ViewSet):
    permission_classes = [IsAuthenticated]

    def create(self, request) -> Response:
        try:
            customer_service = CrmContainer.get_customer_service()
            customer = customer_service.register_customer(data=request.data.copy(), user=request.user, from_form=True)
            
            serializer = CustomerDTO(customer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except DuplicateContactError as dup:
            return _duplicate(dup)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[CustomerController] Falha ao criar lead: {e}")
            return Response(
                {"detail": "Erro interno do servidor."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def list(self, request) -> Response:
        try:
            status_filter = request.query_params.get('actual_status') or request.query_params.get('tag')
            search_term = request.query_params.get('search')
            try:
                page = max(int(request.query_params.get('page', 1)), 1)
                page_size = min(max(int(request.query_params.get('page_size', 10)), 1), 100)
            except (TypeError, ValueError):
                return Response({"detail": "Página inválida."}, status=status.HTTP_400_BAD_REQUEST)

            customer_service = CrmContainer.get_customer_service()
            paginated_customers, total_count = customer_service.page_customers(
                status_filter=status_filter, search_term=search_term,
                custom_tag_filter=request.query_params.get('customer_custom_tag'),
                offset=(page - 1) * page_size, limit=page_size,
            )

            serializer = CustomerDTO(paginated_customers, many=True)
            return Response(
                {"count": total_count, "results": serializer.data},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"[CustomerController] Falha ao listar leads: {e}")
            return Response(
                {"detail": "Erro interno do servidor."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def partial_update(self, request, pk=None) -> Response:
        try:
            if not pk:
                return Response(
                    {"detail": "ID obrigatório."}, status=status.HTTP_400_BAD_REQUEST
                )

            customer_service = CrmContainer.get_customer_service()
            customer = customer_service.update_customer_info(
                customer_id=pk, data=request.data.copy(), user=request.user
            )
            serializer = CustomerDTO(customer)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except DuplicateContactError as dup:
            return _duplicate(dup)
        except PermissionDeniedError as pe:
            return Response({"detail": str(pe)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[CustomerController] Falha no update do lead {pk}: {e}")
            return Response(
                {"detail": "Erro interno do servidor."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def destroy(self, request, pk=None) -> Response:
        # Excluir apaga o contato, que tem conversas, propostas e linha do tempo: só a Erica (admin).
        if not has_role(request.user):
            return Response({"detail": "Só a Erica (admin) exclui leads."}, status=status.HTTP_403_FORBIDDEN)
        try:
            if not pk:
                return Response(
                    {"detail": "ID obrigatório."}, status=status.HTTP_400_BAD_REQUEST
                )

            customer_service = CrmContainer.get_customer_service()
            customer_service.delete_customer(customer_id=pk, user=request.user)

            return Response(status=status.HTTP_204_NO_CONTENT)

        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"[CustomerController] Falha ao deletar lead {pk}: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["post"], permission_classes=[CronOrAuthenticated])
    def process_follow_ups(self, request):
        try:
            customer_service = CrmContainer.get_customer_service()

            customer_service.process_follow_ups()

            return Response(
                {"detail": "Follow-ups processados com sucesso."},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"[CustomerController] Falha ao processar follow-ups: {e}")

            return Response(
                {"detail": "Erro interno do servidor."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def retrieve(self, request, pk=None) -> Response:
        customer = CrmContainer.get_customer_service().customer_repo.get_by_id(pk)
        if not customer:
            return Response({"detail": "Lead não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response(CustomerDTO(customer).data)

    # --- Ações do card do funil ---------------------------------------------------------

    @action(detail=True, methods=['post'])
    @_card_action
    def stage(self, request, pk=None) -> Response:
        """Muda a etapa. Body: {stage, lost_reason (obrigatório para LOST), note}."""
        customer = CrmContainer.get_pipeline_service().change_stage(
            pk, request.data.get('stage'), user=request.user,
            lost_reason=request.data.get('lost_reason'), note=request.data.get('note'),
        )
        return Response(CustomerDTO(customer).data)

    @action(detail=True, methods=['post'])
    @_card_action
    def flags(self, request, pk=None) -> Response:
        """Body: {add: [...], remove: [...]}."""
        customer = CrmContainer.get_pipeline_service().set_flags(
            pk, add=request.data.get('add'), remove=request.data.get('remove'), user=request.user)
        return Response(CustomerDTO(customer).data)

    @action(detail=True, methods=['post'], url_path='next-action')
    @_card_action
    def next_action(self, request, pk=None) -> Response:
        """Body: {next_step, next_action_at (ISO 8601; vazio limpa)}."""
        when = CustomerService()._parse_datetime(request.data.get('next_action_at'))
        if when is not None and when.tzinfo is not None:
            from datetime import timezone
            when = when.astimezone(timezone.utc).replace(tzinfo=None)
        customer = CrmContainer.get_pipeline_service().set_next_action(
            pk, request.data.get('next_step'), when, user=request.user)
        return Response(CustomerDTO(customer).data)

    @action(detail=True, methods=['post'])
    @_card_action
    def notes(self, request, pk=None) -> Response:
        """Nota interna na linha do tempo. Body: {text}."""
        log = CrmContainer.get_pipeline_service().add_note(pk, request.data.get('text'), user=request.user)
        return Response(log, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    @_card_action
    def calls(self, request, pk=None) -> Response:
        """Registra ligação. Body: {outcome: atendeu|nao_atendeu|caixa_postal|numero_invalido|remarcar, notes}."""
        log = CrmContainer.get_pipeline_service().log_call(
            pk, request.data.get('outcome'), request.data.get('notes'), user=request.user)
        return Response(log, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    @_card_action
    def timeline(self, request, pk=None) -> Response:
        return Response(CrmContainer.get_pipeline_service().timeline(pk))

    @action(detail=True, methods=['get', 'post'])
    @_card_action
    def tasks(self, request, pk=None) -> Response:
        """GET: tarefas do lead (?status=pending|done). POST: nova atividade {type, title, due_at (ISO 8601)}."""
        service = CrmContainer.get_sdr_task_service()
        if request.method == 'POST':
            when = CustomerService()._parse_datetime(request.data.get('due_at'))
            if when is not None and when.tzinfo is not None:
                from datetime import timezone
                when = when.astimezone(timezone.utc).replace(tzinfo=None)
            task = service.create_activity(pk, request.data.get('type'), request.data.get('title'), when,
                                           user=request.user)
            return Response(task.to_dict(), status=status.HTTP_201_CREATED)
        status_filter = request.query_params.get('status', 'pending')
        return Response(service.list_tasks(status=status_filter, customer_id=pk))

    # --- Qualificação (mesmos serviços que a IA vai chamar; ver crm/README.md) -------------

    @action(detail=True, methods=['post'], url_path='qualification/start')
    @_card_action
    def qualification_start(self, request, pk=None) -> Response:
        """Body: {product}."""
        customer = CrmContainer.get_lead_qualification_service().start_lead(pk, request.data.get('product'), user=request.user)
        return Response(CustomerDTO(customer).data)

    @action(detail=True, methods=['post'], url_path='qualification/field')
    @_card_action
    def qualification_field(self, request, pk=None) -> Response:
        """Body: {field, value}. "não sei" vira pendência."""
        customer = CrmContainer.get_lead_qualification_service().save_field(
            pk, request.data.get('field'), request.data.get('value'), user=request.user)
        return Response(CustomerDTO(customer).data)

    @action(detail=True, methods=['post'], url_path='qualification/attachment')
    @_card_action
    def qualification_attachment(self, request, pk=None) -> Response:
        """Body: {url, kind: rider|projeto|orcamento_concorrente|lista_pecas|outro, name}."""
        customer = CrmContainer.get_lead_qualification_service().add_attachment(
            pk, request.data.get('url'), request.data.get('kind', 'outro'), request.data.get('name'), user=request.user)
        return Response(CustomerDTO(customer).data)

    @action(detail=True, methods=['post'], url_path='qualification/qualify')
    @_card_action
    def qualification_qualify(self, request, pk=None) -> Response:
        """Body: {pending_fields: [...], needs_erica: bool}."""
        customer = CrmContainer.get_lead_qualification_service().qualify_lead(
            pk, request.data.get('pending_fields') or [], bool(request.data.get('needs_erica')), user=request.user)
        return Response(CustomerDTO(customer).data)

    @action(detail=True, methods=['post'], url_path='human-operator')
    @_card_action
    def human_operator(self, request, pk=None) -> Response:
        """Body: {reason}. Contato vai para a Erica, IA pausada, fora da fila da SDR."""
        customer = CrmContainer.get_lead_qualification_service().mark_human_operator(
            pk, request.data.get('reason') or '', user=request.user)
        return Response(CustomerDTO(customer).data)
