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
        """POST {refresh}: revoga o refresh token do usuário (lista negra), então ele não renova
        mais a sessão mesmo se tiver vazado. O access atual expira sozinho (até 1 h)."""
        self._blacklist_refresh(request)
        try:
            if request.user and request.user.is_authenticated:
                UserService.register_logout(request.user.id)

            return Response({"message": "Logout realizado com sucesso."}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"[AuthController] Falha no processo de logout: {e}")
            return Response({"message": "Sessão encerrada."}, status=status.HTTP_200_OK)

    @staticmethod
    def _blacklist_refresh(request):
        from rest_framework_simplejwt.exceptions import TokenError
        from rest_framework_simplejwt.tokens import RefreshToken

        raw = request.data.get("refresh") if hasattr(request.data, "get") else None
        if not raw or not isinstance(raw, str):
            return
        try:
            token = RefreshToken(raw)
        except TokenError:
            return  # já expirado, já revogado ou inválido: nada a revogar
        if str(token.get("user_id")) != str(request.user.id):
            return  # só revoga o próprio refresh
        token.blacklist()
