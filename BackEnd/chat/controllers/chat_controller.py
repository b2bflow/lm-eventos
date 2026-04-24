from utils.logger import logger
from rest_framework import status
from rest_framework.response import Response
from rest_framework_mongoengine.viewsets import ModelViewSet

from chat.container import ChatContainer
from chat.serializers import ConversationSerializer, MessageSerializer
from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel


class ConversationViewSet(ModelViewSet):
    serializer_class = ConversationSerializer

    def get_queryset(self):
        try:
            conversation_service = ChatContainer.get_conversation_service()
            qs = conversation_service.get_all_conversations()
            return qs if qs is not None else []
        except Exception as e:
            logger.error(f"[ChatController] Erro ao buscar queryset de conversas: {e}")
            return []

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
                conversation = conversation_service.update_conversation(
                    conversation_id=pk,
                    data=request.data
                )

            if not conversation:
                return Response(
                    {"detail": "Conversa não encontrada."},
                    status=status.HTTP_404_NOT_FOUND
                )

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
            return Response(
                {"detail": "Erro interno ao processar solicitação."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )