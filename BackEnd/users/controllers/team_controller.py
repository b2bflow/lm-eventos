from utils.logger import logger
from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from users.services.team_service import TeamService


class TeamController(viewsets.ViewSet):
    def get_permissions(self):
        if self.action in ['create', 'members']:
            return [permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]

    def list(self, request):
        try:
            teams = TeamService.get_all_teams()
            return Response(teams, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"[TeamController] Erro list: {e}")
            return Response({"detail": "Erro interno."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request):
        try:
            team = TeamService.create_team(request.data)
            return Response({"id": str(team.id), "name": team.name}, status=status.HTTP_201_CREATED)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[TeamController] Erro create: {e}")
            return Response({"detail": "Erro interno."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['patch'])
    def members(self, request, pk=None):
        try:
            action_type = request.data.get('action') 
            user_id = request.data.get('user_id')
            
            if not action_type or not user_id:
                return Response({"detail": "Ação e 'user_id' são obrigatórios."}, status=status.HTTP_400_BAD_REQUEST)
                
            TeamService.manage_members(pk, user_id, action_type)
            return Response({"detail": "Membros geridos com sucesso."}, status=status.HTTP_200_OK)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[TeamController] Erro members: {e}")
            return Response({"detail": "Erro interno."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)