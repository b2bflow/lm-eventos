from utils.logger import logger
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from users.serializers import UserDTO
from users.services.user_service import UserService


class UserController(viewsets.ViewSet): 
    
    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]

    def create(self, request):
        serializer = UserDTO(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            novo_usuario = UserService.create_user(serializer.validated_data)
            return Response(UserDTO(novo_usuario).data, status=status.HTTP_201_CREATED)
            
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[UserController] Erro create: {str(e)}", exc_info=True)
            return Response(
                {"detail": "Erro interno no servidor."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        try:
            dto = UserDTO(request.user)
            return Response(dto.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"[UserController] Erro me: {str(e)}")
            return Response(
                {"detail": "Não foi possível carregar perfil."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def online(self, request):
        try:
            data = UserService.get_online_users_list()
            return Response(data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"[UserController] Erro online: {str(e)}")
            return Response([], status=status.HTTP_200_OK)
        
    @action(detail=False, methods=['patch'], url_path='update_profile')
    def update_profile(self, request):
        try:
            updated_user = UserService.update_profile(request.user.id, request.data)
            return Response(UserDTO(updated_user).data, status=status.HTTP_200_OK)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[UserController] Erro update_profile: {str(e)}")
            return Response({"detail": "Erro interno ao atualizar perfil."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='change_password')
    def change_password(self, request):
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        
        if not old_password or not new_password:
            return Response({"detail": "As senhas atual e nova são obrigatórias."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            UserService.change_password(request.user, old_password, new_password)
            return Response({"detail": "Senha atualizada com sucesso!"}, status=status.HTTP_200_OK)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[UserController] Erro change_password: {str(e)}")
            return Response({"detail": "Erro interno ao alterar senha."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    def list(self, request):
        if not request.user.is_staff:
            return Response({"detail": "Acesso negado. Apenas administradores podem ver a equipe."}, status=status.HTTP_403_FORBIDDEN)
            
        try:
            team = UserService.get_team_list()
            return Response(team, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"[UserController] Erro list (team): {str(e)}")
            return Response({"detail": "Erro interno ao buscar equipe."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def partial_update(self, request, pk=None):
        if not request.user.is_staff:
            return Response({"detail": "Acesso negado."}, status=status.HTTP_403_FORBIDDEN)
            
        if str(request.user.id) == str(pk):
            return Response({"detail": "Não podes alterar as tuas próprias permissões de acesso."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            result = UserService.toggle_user_access(pk, request.data)
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[UserController] Erro partial_update: {str(e)}")
            return Response({"detail": "Erro interno ao atualizar acesso."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
