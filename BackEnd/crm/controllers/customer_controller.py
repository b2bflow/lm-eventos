from utils.logger import logger
from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from rest_framework.permissions import IsAuthenticated
from crm.container import CrmContainer
from crm.serializers import CustomerDTO


class CustomerController(ViewSet):
    
    permission_classes = [IsAuthenticated]
    
    def create(self, request) -> Response:
        try:
            customer_service = CrmContainer.get_customer_service()
            customer = customer_service.register_customer(data=request.data.copy(), user=request.user)
            
            serializer = CustomerDTO(customer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[CustomerController] Falha ao criar lead: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def list(self, request) -> Response:
        try:
            status_filter = request.query_params.get('actual_status') or request.query_params.get('tag')
            search_term = request.query_params.get('search')
            page = int(request.query_params.get('page', 1))
            page_size = 10
            
            customer_service = CrmContainer.get_customer_service()
            customers = customer_service.get_active_customers(status_filter=status_filter, search_term=search_term)
            
            total_count = len(customers)
            
            start = (page - 1) * page_size
            end = start + page_size
            paginated_customers = customers[start:end]
            
            serializer = CustomerDTO(paginated_customers, many=True)
            return Response({
                "count": total_count, 
                "results": serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"[CustomerController] Falha ao listar leads: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def partial_update(self, request, pk=None) -> Response:
        try:
            if not pk:
                return Response({"detail": "ID obrigatório."}, status=status.HTTP_400_BAD_REQUEST)
                
            customer_service = CrmContainer.get_customer_service()
            customer = customer_service.update_customer_info(customer_id=pk, data=request.data.copy(), user=request.user)
            serializer = CustomerDTO(customer)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[CustomerController] Falha no update do lead {pk}: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def destroy(self, request, pk=None) -> Response:
        try:
            if not pk:
                return Response({"detail": "ID obrigatório."}, status=status.HTTP_400_BAD_REQUEST)

            customer_service = CrmContainer.get_customer_service()
            customer_service.delete_customer(customer_id=pk, user=request.user)

            return Response(status=status.HTTP_204_NO_CONTENT)

        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"[CustomerController] Falha ao deletar lead {pk}: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
