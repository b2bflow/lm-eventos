from utils.logger import logger
import os
from django.conf import settings
from django.core.files.uploadhandler import MemoryFileUploadHandler
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework_mongoengine.viewsets import ModelViewSet

from chat.container import ChatContainer
from chat.serializers import ConversationSerializer, MessageSerializer
from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from chat.pagination import paginate_desc, parse_page_size
from chat.repositories.conversation_repository import ConversationRepository
from chat.repositories.message_repository import MessageRepository


def _parse_bool(value):
    if value is None or value == '':
        return None
    return str(value).lower() in ('1', 'true', 'yes', 'sim')


class ConversationViewSet(ModelViewSet):
    serializer_class = ConversationSerializer
    queryset = ConversationModel.objects.none()
    lookup_field = 'pk'  # as rotas usam <pk>; o padrão do rest_framework_mongoengine ('id') quebrava o GET por id
    
    def get_queryset(self):
        try:
            conversation_service = ChatContainer.get_conversation_service()
            qs = conversation_service.get_all_conversations()
            return qs if qs is not None else []
        except Exception as e:
            logger.error(f"[ChatController] Erro ao buscar queryset de conversas: {e}")
            return ConversationModel.objects.none()

    def list(self, request, *args, **kwargs) -> Response:
        """Lista paginada por cursor, da conversa mais recente para a mais antiga.

        Query: page_size (padrão 20, máx. 50), cursor, search (nome ou telefone), tag, needs_attention, assignee, ai_qualified,
        status (OPEN ou CLOSED). Resposta: {results, next_cursor, has_more, total}.
        """
        try:
            params = request.query_params
            page_size = parse_page_size(params.get('page_size'), default=20, maximum=50)
            queryset = ConversationRepository.filtered_queryset(
                search=params.get('search'),
                tag=params.get('tag') or None,
                needs_attention=_parse_bool(params.get('needs_attention')),
                status=params.get('status') or None,
                assignee=params.get('assignee') or None,
                ai_qualified=_parse_bool(params.get('ai_qualified')),
            )
            items, next_cursor = paginate_desc(queryset, 'updated_at', params.get('cursor'), page_size)
            serializer = self.get_serializer(items, many=True)
            return Response({
                "results": serializer.data,
                "next_cursor": next_cursor,
                "has_more": bool(next_cursor),
                "total": queryset.count(),
            })
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[ChatController] Erro ao listar conversas: {e}")
            return Response({"detail": "Erro interno."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    def partial_update(self, request, *args, **kwargs) -> Response:
        try:
            pk = kwargs.get('id') or kwargs.get('pk')

            if not pk:
                return Response(
                    {"detail": "ID da conversa não fornecido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            conversation_service = ChatContainer.get_conversation_service()
            mark_read = request.data.get('mark_read')

            if mark_read in [True, 'true', 'True', 1]:
                conversation = conversation_service.mark_conversation_as_read(pk)
            else:
                data = dict(request.data)
                if 'tag' in data:
                    # Alternador IA/humano da lista: mesma regra e registro do botão Retomar IA.
                    ChatContainer.get_handover_service().set_mode(pk, data.pop('tag'), user=request.user)
                if 'assignee' in data:
                    ChatContainer.get_handover_service().assign(pk, data.pop('assignee'), user=request.user)
                conversation = conversation_service.update_conversation(conversation_id=pk, data=data)

            if not conversation:
                return Response({"detail": "Conversa não encontrada."}, status=status.HTTP_404_NOT_FOUND)

            serializer = self.get_serializer(conversation)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"[ChatController] Erro no update da conversa {pk}: {e}")
            return Response(
                {"detail": "Erro interno."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def search_contacts(self, request, *args, **kwargs) -> Response:
        try:
            search_term = request.query_params.get('search', '')
            conversation_status = request.query_params.get('status', 'OPEN').upper()
            conversation_service = ChatContainer.get_conversation_service()
            matches = conversation_service.search_contacts(search_term, conversation_status)

            results = []
            for match in matches:
                customer = match['customer']
                conversation = match['conversation']
                results.append({
                    'customer': str(customer.id),
                    'customer_name': customer.name or 'Desconhecido',
                    'customer_phone': customer.phone or 'Sem Número',
                    'customer_status': customer.customer_state_now or 'ANALYSIS',
                    'conversation': ConversationSerializer(conversation).data if conversation else None,
                })

            return Response({'results': results}, status=status.HTTP_200_OK)
        except ValueError as ve:
            return Response({'detail': str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[ChatController] Erro na busca de contatos: {e}")
            return Response({'detail': 'Erro interno.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def start_conversation(self, request, *args, **kwargs) -> Response:
        try:
            customer_id = request.data.get('customer_id')
            if not customer_id:
                return Response(
                    {'detail': 'ID do contato é obrigatório.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            conversation_service = ChatContainer.get_conversation_service()
            conversation, created = conversation_service.start_conversation(customer_id)
            serializer = self.get_serializer(conversation)
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            )
        except ValueError as ve:
            return Response({'detail': str(ve)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"[ChatController] Erro ao iniciar conversa: {e}")
            return Response({'detail': 'Erro interno.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MessageViewSet(ModelViewSet):
    serializer_class = MessageSerializer
    pagination_class = None

    def get_queryset(self):
        try:
            if not hasattr(self, "request"):
                return []

            customer_id = self.request.query_params.get('customer')
            conversation_id = self.request.query_params.get('conversation')

            message_service = ChatContainer.get_message_service()

            if customer_id:
                qs = message_service.get_messages_by_customer(customer_id)
                return qs if qs is not None else []

            if conversation_id:
                qs = message_service.get_messages_by_conversation(conversation_id)
                return qs if qs is not None else []

            return []

        except Exception as e:
            logger.error(f"[ChatController] Erro ao buscar queryset de mensagens: {e}")
            return []

    def list(self, request, *args, **kwargs) -> Response:
        """Mensagens de uma conversa (ou de todas as conversas do cliente), das mais novas para as antigas.

        Query: conversation ou customer, page_size (padrão 30, máx. 100), cursor (next_cursor da página anterior).
        Cada página vem em ordem cronológica (antiga -> nova) para exibir direto no chat.
        Resposta: {results, next_cursor, has_more}.
        """
        try:
            params = request.query_params
            customer_id = params.get('customer')
            conversation_id = params.get('conversation')
            if not customer_id and not conversation_id:
                return Response({"results": [], "next_cursor": None, "has_more": False})
            page_size = parse_page_size(params.get('page_size'), default=30, maximum=100)
            queryset = MessageRepository.queryset_for(conversation_id=conversation_id, customer_id=customer_id)
            items, next_cursor = paginate_desc(queryset, 'created_at', params.get('cursor'), page_size)
            serializer = self.get_serializer(list(reversed(items)), many=True)
            return Response({"results": serializer.data, "next_cursor": next_cursor, "has_more": bool(next_cursor)})
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[ChatController] Erro ao listar mensagens: {e}")
            return Response({"detail": "Erro interno."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request, *args, **kwargs) -> Response:
        try:
            conversation_id = request.data.get('conversation_id')
            content = request.data.get('content')

            if not conversation_id or not content:
                return Response(
                    {"detail": "Dados incompletos."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            message_service = ChatContainer.get_message_service()

            message_service.execute_operator_message(
                conversation_id=conversation_id,
                content=content,
                sender_id=str(request.user.id) if request.user else "SYSTEM"
            )

            return Response(
                {"status": "queued"},
                status=status.HTTP_202_ACCEPTED
            )

        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.error(f"[ChatController] Create error: {e}")
            return Response({"detail": "Erro interno ao processar solicitação."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MessageFileUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs) -> Response:
        try:
            max_upload_mb = int(os.getenv("CHAT_FILE_UPLOAD_MAX_MB", "15"))
            configured_max_bytes = max_upload_mb * 1024 * 1024
            django_memory_limit = getattr(settings, "FILE_UPLOAD_MAX_MEMORY_SIZE", configured_max_bytes)
            max_upload_bytes = min(configured_max_bytes, django_memory_limit)
            effective_max_mb = max_upload_bytes // (1024 * 1024)

            if request.META.get("CONTENT_LENGTH"):
                content_length = int(request.META["CONTENT_LENGTH"])
                if content_length > max_upload_bytes:
                    return Response(
                        {"detail": f"Arquivo excede o limite de {effective_max_mb}MB."},
                        status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    )

            request._request.upload_handlers = [
                MemoryFileUploadHandler(request._request)
            ]

            conversation_id = request.data.get("conversation_id")
            uploaded_file = request.FILES.get("file")
            caption = request.data.get("caption") or None

            if not conversation_id or not uploaded_file:
                return Response(
                    {"detail": "conversation_id e file são obrigatórios."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if uploaded_file.size > max_upload_bytes:
                return Response(
                    {"detail": f"Arquivo excede o limite de {effective_max_mb}MB."},
                    status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                )

            message_service = ChatContainer.get_message_service()
            message = message_service.execute_operator_file(
                conversation_id=conversation_id,
                uploaded_file=uploaded_file,
                sender_id=str(request.user.id) if request.user else "SYSTEM",
                caption=caption,
            )

            return Response(
                {
                    "status": "sent",
                    "message_id": str(message.id),
                    "external_id": message.external_id,
                },
                status=status.HTTP_201_CREATED,
            )

        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"[ChatController] File upload error: {e}")
            return Response(
                {"detail": "Erro interno ao enviar arquivo."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


def _team_action(fn):
    """400 (regra), 500 (inesperado) para as ações da equipe na conversa."""
    def wrapper(self, request, pk):
        try:
            return fn(self, request, pk)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[ChatController] Falha em {fn.__name__} da conversa {pk}: {e}")
            return Response({"detail": "Erro interno."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    wrapper.__name__ = fn.__name__
    return wrapper


class ConversationModeController(APIView):
    """POST /chat/conversations/<id>/mode/ {mode: AGENTE (retomar IA) | OPERADOR (assumir)}."""
    permission_classes = [IsAuthenticated]

    @_team_action
    def post(self, request, pk):
        conversation = ChatContainer.get_handover_service().set_mode(pk, request.data.get('mode'), user=request.user)
        return Response(ConversationSerializer(conversation).data)


class ConversationAssignController(APIView):
    """POST /chat/conversations/<id>/assign/ {assignee: sdr | erica | lucia | null}."""
    permission_classes = [IsAuthenticated]

    @_team_action
    def post(self, request, pk):
        conversation = ChatContainer.get_handover_service().assign(pk, request.data.get('assignee'), user=request.user)
        return Response(ConversationSerializer(conversation).data)


class ConversationNoteController(APIView):
    """POST /chat/conversations/<id>/notes/ {text}: nota interna (conversa e linha do tempo do card)."""
    permission_classes = [IsAuthenticated]

    @_team_action
    def post(self, request, pk):
        log = ChatContainer.get_handover_service().add_note(pk, request.data.get('text'), user=request.user)
        return Response(log, status=status.HTTP_201_CREATED)


class ConversationCallController(APIView):
    """POST /chat/conversations/<id>/calls/ {outcome, notes}: registra a ligação feita pelo botão Ligar."""
    permission_classes = [IsAuthenticated]

    @_team_action
    def post(self, request, pk):
        log = ChatContainer.get_handover_service().log_call(
            pk, request.data.get('outcome'), request.data.get('notes'), user=request.user)
        return Response(log, status=status.HTTP_201_CREATED)
