from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from crm import domain
from crm.container import CrmContainer
from crm.models.lm_settings_model import LmSettings
from crm.models.sdr_task_model import TASK_TYPES
from crm.services.pipeline_service import CALL_OUTCOMES
from users.permissions import has_role
from utils.logger import logger


def _bool(value) -> bool:
    return str(value).lower() in ('1', 'true', 'yes', 'sim')


class FunnelBoardController(APIView):
    """GET /crm/funnel/: colunas por etapa, paginadas no banco.

    Query: product, owner, flag, search, include_human (operador humano fica fora por padrão),
    ai_qualified (só leads qualificados pela IA), archived (aba "Arquivados": só ganho e perdido),
    per_stage (padrão 30, máx. 100), stage + offset para carregar mais de uma coluna.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = request.query_params
        try:
            per_stage = min(max(int(params.get('per_stage', 30)), 1), 100)
            stage = params.get('stage')
            if stage and stage not in domain.STAGES:
                return Response({"detail": "Etapa inválida."}, status=status.HTTP_400_BAD_REQUEST)
            board = CrmContainer.get_pipeline_service().board(
                stages=[stage] if stage else None,
                per_stage=per_stage,
                offsets={stage: params.get('offset', 0)} if stage else None,
                product=params.get('product') or None,
                owner=params.get('owner') or None,
                flag=params.get('flag') or None,
                search=params.get('search') or None,
                include_human=_bool(params.get('include_human')),
                ai_qualified=_bool(params.get('ai_qualified')),
                archived=_bool(params.get('archived')),
            )
            return Response(board)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[FunnelBoard] Erro ao montar o funil: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FunnelListController(APIView):
    """GET /crm/funnel/list/: o funil em lista (mesmos filtros do quadro), paginado.

    Query: os filtros do quadro + stage (opcional), offset e limit (padrão 50, máx. 200).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = request.query_params
        try:
            stage = params.get('stage') or None
            if stage and stage not in domain.STAGES:
                return Response({"detail": "Etapa inválida."}, status=status.HTTP_400_BAD_REQUEST)
            data = CrmContainer.get_pipeline_service().lead_list(
                offset=int(params.get('offset', 0) or 0),
                limit=min(max(int(params.get('limit', 50)), 1), 200),
                stage=stage,
                product=params.get('product') or None,
                owner=params.get('owner') or None,
                flag=params.get('flag') or None,
                search=params.get('search') or None,
                include_human=_bool(params.get('include_human')),
                ai_qualified=_bool(params.get('ai_qualified')),
                archived=_bool(params.get('archived')),
            )
            return Response(data)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[FunnelList] Erro ao listar o funil: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FunnelMetaController(APIView):
    """GET /crm/meta/: listas de valores do card (etapas, produtos, flags...) para o frontend."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "stages": [{"key": s, "label": domain.STAGE_LABELS[s]} for s in domain.STAGES],
            "transitions": {k: sorted(v) for k, v in domain.TRANSITIONS.items()},
            "products": domain.PRODUCTS,
            "owners": domain.OWNERS,
            "contact_types": domain.CONTACT_TYPES,
            "origins": domain.ORIGINS,
            "flags": domain.FLAGS,
            "lost_reasons": domain.LOST_REASONS,
            "attachment_kinds": domain.ATTACHMENT_KINDS,
            "call_outcomes": CALL_OUTCOMES,
            "task_types": TASK_TYPES,
        })


class SdrTaskController(APIView):
    """GET /crm/tasks/?status=pending: fila da SDR por prazo. POST /crm/tasks/<id>/done/ conclui."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        status_filter = request.query_params.get('status', 'pending')
        return Response(CrmContainer.get_sdr_task_service().list_tasks(status=status_filter, limit=200))

    def post(self, request, task_id=None):
        try:
            task = CrmContainer.get_sdr_task_service().complete(task_id, user=request.user)
            return Response(task.to_dict())
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_404_NOT_FOUND)


class LmSettingsController(APIView):
    """GET /crm/settings/ (qualquer usuário autenticado) e PATCH (só admin)."""
    permission_classes = [IsAuthenticated]

    READ_ONLY = {"key", "updated_at", "google_connected", *LmSettings.SECRET_FIELDS}

    def get(self, request):
        return Response(LmSettings.get().to_dict())

    def patch(self, request):
        if not has_role(request.user):
            return Response({"detail": "Só a Erica (admin) altera as configurações."}, status=status.HTTP_403_FORBIDDEN)
        settings = LmSettings.get()
        try:
            for key, value in request.data.items():
                if key in self.READ_ONLY or key not in settings._fields:
                    continue
                setattr(settings, key, value)
            from datetime import datetime
            settings.updated_at = datetime.utcnow()
            settings.validate()
            settings.save()
            return Response(settings.to_dict())
        except Exception as e:
            return Response({"detail": f"Configuração inválida: {e}"}, status=status.HTTP_400_BAD_REQUEST)


class WhatsAppGroupsController(APIView):
    """GET /crm/settings/whatsapp-groups/ (só admin): grupos do número da LM na Z-API, para escolher o
    grupo de atendimento sem precisar caçar o id no log."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not has_role(request.user):
            return Response({"detail": "Só a Erica (admin) vê os grupos."}, status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(CrmContainer.get_notification_service().chat.list_groups())
        except Exception as e:
            logger.error(f"[WhatsAppGroups] Falha ao listar grupos na Z-API: {e}")
            return Response({"detail": "Não foi possível buscar os grupos na Z-API."},
                            status=status.HTTP_502_BAD_GATEWAY)
