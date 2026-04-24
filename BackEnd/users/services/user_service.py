from utils.logger import logger
from datetime import timedelta
from django.utils import timezone
from typing import Optional, List, Dict
from users.repositories.user_repository import UserRepository
from users.models import User


class UserService:
    
    @classmethod
    def create_user(self, data: dict) -> User:
        if not data.get('username') or not data.get('password'):
            raise ValueError("Username e Password são obrigatórios.")

        user = UserRepository.create_user(data)
        if not user:
            raise ValueError("Não foi possível criar o usuário. Verifique se o nome de usuário já existe.")
        
        logger.info(f"Novo usuário criado: {user.username}")
        return user

    @classmethod
    def get_online_users_list(self) -> List[Dict]:
        try:
            now = timezone.now()
            threshold = now - timedelta(minutes=10)
            
            users = UserRepository.get_active_users_filter_last_login(threshold)
            result = []
            
            online_threshold = now - timedelta(minutes=2)

            for u in users:
                is_online = u.last_login and u.last_login >= online_threshold
                result.append({
                    "id": u.id,
                    "first_name": u.first_name, 
                    "username": u.username,
                    "status": "ONLINE" if is_online else "INATIVO", 
                    "is_online": is_online
                })
            return result
        except Exception as e:
            logger.error(f"[UserService] Erro ao listar online: {str(e)}")
            return []
    
    @classmethod
    def get_user_name(self, user_id: int | str) -> str:
        user = UserRepository.get_by_id(user_id)
        if user:
            return user.first_name or user.username
        return "Usuário Desconhecido"

    @classmethod
    def get_user_by_id(self, user_id: int | str) -> Optional[User]:
        return UserRepository.get_by_id(user_id)
    
    @classmethod
    def update_profile(self, user_id: int, data: dict) -> User:
        user = UserRepository.update_user_profile(user_id, data)
        if not user:
            raise ValueError("Usuário não encontrado.")
        return user

    @classmethod
    def change_password(self, user: User, old_password: str, new_password: str) -> bool:
        if not user.check_password(old_password):
            raise ValueError("A senha atual informada está incorreta.")
            
        if len(new_password) < 6:
            raise ValueError("A nova senha deve ter pelo menos 6 caracteres.")
            
        success = UserRepository.update_password(user.id, new_password)
        if not success:
            raise ValueError("Erro ao salvar a nova senha no banco.")
            
        logger.info(f"[UserService] Senha alterada com sucesso para o usuário: {user.username}")
        return True
    
    @classmethod
    def get_team_list(self) -> List[Dict]:
        users = UserRepository.get_all_users()
        result = []
        for u in users:
            result.append({
                "id": u.id,
                "name": u.first_name or u.username,
                "email": u.email,
                "role": "ADMIN" if u.is_staff else "OPERATOR",
                "status": "ACTIVE" if u.is_active else "INACTIVE"
            })
        return result

    @classmethod
    def toggle_user_access(self, user_id: int, data: dict) -> Dict:
        is_staff = data.get('is_staff')
        is_active = data.get('is_active')
        
        if is_staff is None and is_active is None:
            raise ValueError("Nenhum parâmetro de atualização foi fornecido.")
            
        updated_user = UserRepository.update_user_access(user_id, is_staff=is_staff, is_active=is_active)
        
        if not updated_user:
            raise ValueError("Usuário não encontrado.")
            
        logger.info(f"[UserService] Acessos atualizados para o usuário: {updated_user.username}")
        
        return {
            "id": updated_user.id,
            "role": "ADMIN" if updated_user.is_staff else "OPERATOR",
            "status": "ACTIVE" if updated_user.is_active else "INACTIVE"
        }
    
    @classmethod
    def register_logout(self, user_id: int) -> None:
        try:
            past_date = timezone.now() - timedelta(days=365)
            UserRepository.update_last_login(user_id, past_date)
            logger.info(f"[UserService] Logout registrado para o ID: {user_id}")
        except Exception as e:
            logger.error(f"[UserService] Erro ao registrar logout: {e}")