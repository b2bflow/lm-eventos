from utils.logger import logger
from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from users.services.request_service import NameRequestService


class NameRequestController(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        if request.user.is_staff:
            requests = NameRequestService.get_admin_pending_requests()
            data = [{
                "id": req.id,
                "current_name": req.user.first_name,
                "new_name": req.new_name,
                "user_email": req.user.email,
                "created_at": req.created_at
            } for req in requests]
            return Response(data, status=status.HTTP_200_OK)
        else:
            has_pending = NameRequestService.check_user_pending_request(request.user)
            return Response({"has_pending": has_pending}, status=status.HTTP_200_OK)

    def create(self, request):
        try:
            new_name = request.data.get('new_name')
            NameRequestService.request_name_change(request.user, new_name)
            return Response({"detail": "Solicitação enviada com sucesso."}, status=status.HTTP_201_CREATED)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[RequestController] Erro create: {e}")
            return Response({"detail": "Erro interno."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def partial_update(self, request, pk=None):
        try:
            action = request.data.get('action') 
            NameRequestService.process_request(pk, action, request.user)
            return Response({"detail": f"Solicitação {action.lower()} com sucesso."}, status=status.HTTP_200_OK)
        except PermissionError as pe:
            return Response({"detail": str(pe)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[RequestController] Erro update: {e}")
            return Response({"detail": "Erro interno."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)