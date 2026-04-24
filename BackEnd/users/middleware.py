from utils.logger import logger
from datetime import timedelta
from django.utils import timezone
from users.repositories.user_repository import UserRepository
from typing import Callable
from django.http import HttpRequest, HttpResponse


class UpdateLastLoginMiddleware:
    
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path.endswith('/logout/'):
            return self.get_response(request)

        response = self.get_response(request)

        if request.user.is_authenticated:
            try:
                now = timezone.now()
                user_last_login = request.user.last_login
                
                should_update = not user_last_login or (now - user_last_login > timedelta(minutes=2))
                
                if should_update:
                    UserRepository.update_last_login(request.user.id, now)
                    
            except Exception as e:
                logger.error(f"[UpdateLastLoginMiddleware] Falha ao atualizar timestamp de atividade: {str(e)}")

        return response