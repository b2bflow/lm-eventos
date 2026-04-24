from django.db import transaction
from utils.logger import logger
from users.models.user_model import NameChangeRequest


class NameRequestRepository:
    @staticmethod
    def create_request(user, new_name: str) -> NameChangeRequest:
        try:
            req = NameChangeRequest(user=user, new_name=new_name, status='PENDING')
            req.save()
            return req
        except Exception as e:
            logger.error(f"[NameRequestRepository] Erro ao criar request: {e}")
            raise e

    @staticmethod
    def has_pending_request(user) -> bool:
        return NameChangeRequest.objects.filter(user=user, status='PENDING').exists()

    @staticmethod
    def get_pending_requests():
        return NameChangeRequest.objects.filter(status='PENDING').select_related('user')

    @staticmethod
    def get_by_id(request_id: int) -> NameChangeRequest | None:
        return NameChangeRequest.objects.filter(id=request_id).first()

    @staticmethod
    def reject_request(request: NameChangeRequest) -> NameChangeRequest:
        try:
            request.status = 'REJECTED'
            request.save()
            return request
        except Exception as e:
            logger.error(f"[NameRequestRepository] Erro ao rejeitar request: {e}")
            raise e

    @staticmethod
    @transaction.atomic  
    def approve_request(request: NameChangeRequest) -> NameChangeRequest:
        try:
            request.status = 'APPROVED'
            request.save()
            
            user = request.user
            user.first_name = request.new_name
            user.save()
            
            return request
        except Exception as e:
            logger.error(f"[NameRequestRepository] Falha crítica ao aprovar request: {e}")
            raise e