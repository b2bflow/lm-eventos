from utils.logger import logger
from users.repositories.request_repository import NameRequestRepository


class NameRequestService:
    @staticmethod
    def request_name_change(user, new_name: str):
        if not new_name or len(new_name.strip()) < 2:
            raise ValueError("O novo nome deve ter pelo menos 2 caracteres.")
            
        if user.first_name == new_name:
            raise ValueError("O novo nome deve ser diferente do atual.")
            
        if NameRequestRepository.has_pending_request(user):
            raise ValueError("Você já possui uma solicitação de alteração em análise.")
            
        logger.info(f"[NameRequestService] Utilizador {user.email} solicitou troca para '{new_name}'")
        return NameRequestRepository.create_request(user, new_name)

    @staticmethod
    def process_request(request_id: int, action: str, admin_user):
        if not admin_user.is_staff:
            raise PermissionError("Apenas administradores podem processar solicitações.")
            
        req = NameRequestRepository.get_by_id(request_id)
        if not req:
            raise ValueError("Solicitação não encontrada.")
            
        if req.status != 'PENDING':
            raise ValueError(f"Esta solicitação já foi processada ({req.status}).")

        if action == 'APPROVE':
            NameRequestRepository.approve_request(req)
            logger.info(f"[NameRequestService] Admin {admin_user.email} APROVOU troca para '{req.new_name}'")
            
        elif action == 'REJECT':
            NameRequestRepository.reject_request(req)
            logger.info(f"[NameRequestService] Admin {admin_user.email} REJEITOU troca para '{req.new_name}'")
            
        else:
            raise ValueError("Ação inválida. Use 'APPROVE' ou 'REJECT'.")
            
        return req
    
    @staticmethod
    def get_admin_pending_requests():
        return NameRequestRepository.get_pending_requests()