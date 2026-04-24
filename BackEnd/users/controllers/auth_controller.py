from utils.logger import logger
from rest_framework_simplejwt.views import TokenObtainPairView
from users.serializers import CustomTokenObtainPairSerializer
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from users.services.user_service import UserService


class LoginRateThrottle(AnonRateThrottle):
    rate = '10/minute' 

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]

class AuthController(viewsets.ViewSet):
    @action(detail=False, methods=['post'], url_path='logout')
    def logout(self, request):
        try:
            if request.user and request.user.is_authenticated:
                UserService.register_logout(request.user.id)
            
            return Response({"message": "Logout realizado com sucesso."}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"[AuthController] Falha no processo de logout: {e}")
            return Response({"message": "Sessão encerrada."}, status=status.HTTP_200_OK)