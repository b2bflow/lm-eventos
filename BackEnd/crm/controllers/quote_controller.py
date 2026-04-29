from utils.logger import logger
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from crm.container import CrmContainer
from crm.serializers import QuoteDTO


class QuoteController(ViewSet):
    permission_classes = [IsAuthenticated]

    def create(self, request) -> Response:
        try:
            quote_service = CrmContainer.get_quote_service()
            quote = quote_service.create_quote(data=request.data.copy(), user=request.user)
            serializer = QuoteDTO(quote)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[QuoteController] Falha ao criar cotação: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def list(self, request) -> Response:
        try:
            status_filter = request.query_params.get("actual_status") or request.query_params.get("tag")
            search_term = request.query_params.get("search")
            page = int(request.query_params.get("page", 1))
            page_size = 10

            quote_service = CrmContainer.get_quote_service()
            quotes = quote_service.list_quotes(status_filter=status_filter, search_term=search_term)

            total_count = len(quotes)
            start = (page - 1) * page_size
            end = start + page_size
            serializer = QuoteDTO(quotes[start:end], many=True)
            return Response({"count": total_count, "results": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"[QuoteController] Falha ao listar cotações: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def partial_update(self, request, pk=None) -> Response:
        try:
            if not pk:
                return Response({"detail": "ID obrigatório."}, status=status.HTTP_400_BAD_REQUEST)

            quote_service = CrmContainer.get_quote_service()
            quote = quote_service.update_quote(quote_id=pk, data=request.data.copy(), user=request.user)
            serializer = QuoteDTO(quote)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[QuoteController] Falha ao atualizar cotação {pk}: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None) -> Response:
        try:
            if not pk:
                return Response({"detail": "ID obrigatório."}, status=status.HTTP_400_BAD_REQUEST)

            quote_service = CrmContainer.get_quote_service()
            status_value = request.data.get("status") or request.data.get("customer_state_now")
            quote = quote_service.close_quote(
                quote_id=pk,
                status_value=status_value,
                data=request.data.copy(),
                user=request.user,
            )
            serializer = QuoteDTO(quote)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[QuoteController] Falha ao fechar cotação {pk}: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def destroy(self, request, pk=None) -> Response:
        try:
            if not pk:
                return Response({"detail": "ID obrigatório."}, status=status.HTTP_400_BAD_REQUEST)
            quote_service = CrmContainer.get_quote_service()
            quote_service.delete_quote(pk)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.error(f"[QuoteController] Falha ao deletar cotação {pk}: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
